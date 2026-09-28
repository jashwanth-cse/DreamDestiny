"""
Message Understanding Engine for the WhatsApp Bot.
Follows Section 6 of the specification:
1. Fast, deterministic regex/keyword parsing first.
2. Safe LLM fallback when natural language extraction is needed.
3. Strict Pydantic validation of all extracted slots.
"""

import re
import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from app.schemas.trip import BudgetLevel, TransportPref, HotelPref
from app.understanding.schemas import ExtractedTripSlots
from app.config import settings

logger = logging.getLogger(__name__)

# Optional Google Generative AI import
try:
    import google.generativeai as genai
except ImportError:
    genai = None


class MessageParser:
    def __init__(self, gemini_api_key: Optional[str] = settings.gemini_api_key):
        self._gemini_api_key = gemini_api_key
        self._llm = None
        if genai and gemini_api_key:
            try:
                genai.configure(api_key=gemini_api_key)
                self._llm = genai.GenerativeModel("gemini-1.5-flash")
            except Exception as e:
                logger.warning("Could not initialize Gemini LLM for message understanding: %s", e)

    def parse_deterministic(self, text: str, payload_id: Optional[str] = None) -> ExtractedTripSlots:
        """Rule-based, instant regex and button extraction."""
        slots = ExtractedTripSlots()
        clean_text = text.strip()
        lower = clean_text.lower()

        # 1. Confirmation / Rejection Intent
        if (
            payload_id == "btn_confirm"
            or lower in ("yes", "confirm", "proceed", "looks good", "generate", "plan it", "go ahead")
        ):
            slots.confirmation_intent = True
            return slots
        elif payload_id == "btn_cancel" or lower in ("no", "cancel trip", "abort"):
            slots.confirmation_intent = False
            slots.reset_intent = True
            return slots

        # 2. Reset / Start Over Intent
        if lower in ("reset", "restart", "start over", "cancel", "new trip", "clear"):
            slots.reset_intent = True
            return slots

        # 3. Interactive Button Payloads
        if payload_id:
            if payload_id == "btn_transport_train":
                slots.transport_mode = TransportPref.train
            elif payload_id == "btn_transport_bus":
                slots.transport_mode = TransportPref.bus
            elif payload_id == "btn_transport_flight":
                slots.transport_mode = TransportPref.flight
            elif payload_id == "btn_transport_any":
                slots.transport_mode = TransportPref.any
            elif payload_id == "btn_budget_low":
                slots.budget_level = BudgetLevel.low
            elif payload_id == "btn_budget_medium":
                slots.budget_level = BudgetLevel.medium
            elif payload_id == "btn_budget_high":
                slots.budget_level = BudgetLevel.high
            elif payload_id == "btn_hotel_budget":
                slots.hotel_category = HotelPref.budget
            elif payload_id == "btn_hotel_mid":
                slots.hotel_category = HotelPref.mid_range
            elif payload_id == "btn_hotel_luxury":
                slots.hotel_category = HotelPref.luxury
            elif payload_id == "btn_hotel_any":
                slots.hotel_category = HotelPref.any

        # 4. Keyword Transport / Budget / Hotel mapping
        if not slots.transport_mode:
            if re.search(r"\b(train|railway|irctc)\b", lower):
                slots.transport_mode = TransportPref.train
            elif re.search(r"\b(bus|redbus|coach)\b", lower):
                slots.transport_mode = TransportPref.bus
            elif re.search(r"\b(flight|fly|plane|air)\b", lower):
                slots.transport_mode = TransportPref.flight
            elif re.search(r"\b(any transport|any mode)\b", lower):
                slots.transport_mode = TransportPref.any

        if not slots.budget_level:
            if re.search(r"\b(low budget|cheap|budget friendly|economy)\b", lower):
                slots.budget_level = BudgetLevel.low
            elif re.search(r"\b(medium budget|mid[- ]?range|moderate)\b", lower):
                slots.budget_level = BudgetLevel.medium
            elif re.search(r"\b(luxury|high budget|expensive|premium|5[- ]?star)\b", lower):
                slots.budget_level = BudgetLevel.high

        if not slots.hotel_category:
            if re.search(r"\b(budget hotel|hostel|dorm|cheap hotel)\b", lower):
                slots.hotel_category = HotelPref.budget
            elif re.search(r"\b(mid[- ]?range hotel|3[- ]?star)\b", lower):
                slots.hotel_category = HotelPref.mid_range
            elif re.search(r"\b(luxury hotel|resort|4[- ]?star|5[- ]?star)\b", lower):
                slots.hotel_category = HotelPref.luxury

        # 5. Travelers Count
        travelers_match = re.search(r"\b(\d+)\s*(?:people|persons?|travelers?|adults?|passengers?)\b", lower)
        if travelers_match:
            slots.travelers = min(max(int(travelers_match.group(1)), 1), 20)
        elif re.search(r"\b(solo|myself|alone|just me)\b", lower):
            slots.travelers = 1
        elif re.search(r"\b(couple|two of us|me and my (wife|husband|friend))\b", lower):
            slots.travelers = 2

        # 6. Duration
        duration_match = re.search(r"\b(\d+)\s*(?:days?|nights?)\b", lower)
        if duration_match:
            slots.duration_days = int(duration_match.group(1))

        # 7. Date Matching (YYYY-MM-DD, DD-MM-YYYY, or YYYY/MM/DD)
        date_iso = re.search(r"\b(\d{4}[-/]\d{1,2}[-/]\d{1,2})\b", lower)
        date_dmy = re.search(r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{4})\b", lower)
        if date_iso:
            try:
                raw_d = date_iso.group(1).replace("/", "-")
                parsed = datetime.strptime(raw_d, "%Y-%m-%d").date()
                if parsed >= date.today():
                    slots.start_date = parsed
            except ValueError:
                pass
        elif date_dmy:
            try:
                raw_d = date_dmy.group(1).replace("/", "-")
                parsed = datetime.strptime(raw_d, "%d-%m-%Y").date()
                if parsed >= date.today():
                    slots.start_date = parsed
            except ValueError:
                pass

        # If start_date and duration_days found, compute end_date automatically
        if slots.start_date and slots.duration_days and not slots.end_date:
            slots.end_date = slots.start_date + timedelta(days=slots.duration_days)

        # 8. Origin & Destination Extraction
        # Pattern A: "from <Origin> to <Destination>"
        from_to_match = re.search(r"\bfrom\s+([A-Za-z\s]+?)\s+to\s+([A-Za-z\s]+?)(?:\s+on|\s+for|\s+with|\s+in|$)", text, re.IGNORECASE)
        if from_to_match:
            slots.origin = from_to_match.group(1).strip().title()
            slots.destination = from_to_match.group(2).strip().title()
        else:
            # Pattern B: "to <Destination>" or "trip to <Destination>"
            to_match = re.search(r"\b(?:to|visiting|trip to|visit)\s+([A-Za-z\s]+?)(?:\s+from|\s+on|\s+for|\s+with|\s+in|$)", text, re.IGNORECASE)
            if to_match and not slots.destination:
                dest_candidate = to_match.group(1).strip()
                if len(dest_candidate) >= 3 and dest_candidate.lower() not in ("chennai", "delhi", "mumbai", "train", "bus", "flight"):
                    slots.destination = dest_candidate.title()

            from_match = re.search(r"\bfrom\s+([A-Za-z\s]+?)(?:\s+to|\s+on|\s+for|\s+with|\s+in|$)", text, re.IGNORECASE)
            if from_match and not slots.origin:
                slots.origin = from_match.group(1).strip().title()

        # 9. Modification Intent
        if any(mod in lower for mod in ("make it cheaper", "cheaper hotel", "change transport", "switch to", "add more", "change date")):
            slots.modification_intent = clean_text

        return slots

    async def parse(self, text: str, payload_id: Optional[str] = None) -> ExtractedTripSlots:
        """
        Parses user input using deterministic rules first.
        Falls back to LLM JSON extraction only if deterministic rules found nothing on conversational input.
        """
        slots = self.parse_deterministic(text, payload_id)
        if slots.has_slots():
            return slots

        # If deterministic rules didn't catch anything and LLM is enabled, invoke structured parsing
        if self._llm and len(text.strip().split()) >= 3:
            try:
                return await self._parse_with_llm(text)
            except Exception as e:
                logger.warning("LLM extraction failed: %s. Using default empty slots.", e)

        return slots

    async def _parse_with_llm(self, text: str) -> ExtractedTripSlots:
        """Structured Gemini JSON extraction for complex travel phrases."""
        prompt = f"""
        Extract travel intent parameters from the following user message.
        Output ONLY valid JSON with keys:
        - origin: string or null
        - destination: string or null
        - start_date: YYYY-MM-DD or null
        - end_date: YYYY-MM-DD or null
        - duration_days: integer or null
        - travelers: integer or null
        - budget_level: "low", "medium", "high", or null
        - transport_mode: "train", "bus", "flight", "any", or null
        - hotel_category: "budget", "mid_range", "luxury", or null
        - interests: list of strings (e.g. ["beaches", "temples"])

        User message: "{text}"
        """
        response = await self._llm.generate_content_async(prompt)
        raw_text = response.text.strip()
        # Clean markdown fences
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text)
        data = json.loads(raw_text)
        return ExtractedTripSlots.model_validate(data)


message_parser = MessageParser()
