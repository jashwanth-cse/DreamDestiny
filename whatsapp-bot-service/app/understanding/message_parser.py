"""
Message Understanding Engine for the WhatsApp Bot.
Provides high-resilience natural language parsing combining:
1. Instant deterministic parsing with comprehensive Indian travel & date expressions.
2. Context-aware slot mapping (knowing which question was asked).
3. State-of-the-art Gemini 2.5 Flash structured JSON fallback for complex conversational requests.
"""

import re
import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

from app.schemas.conversation import ConversationState
from app.schemas.trip import BudgetLevel, TransportPref, HotelPref, TripDraft
from app.understanding.schemas import ExtractedTripSlots
from app.config import settings

logger = logging.getLogger(__name__)

# Optional Google Generative AI import
try:
    import google.generativeai as genai
except ImportError:
    genai = None

MONTH_NAMES = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12
}


class MessageParser:
    def __init__(self, gemini_api_key: Optional[str] = settings.gemini_api_key):
        self._gemini_api_key = gemini_api_key
        self._llm = None
        if genai and gemini_api_key:
            try:
                genai.configure(api_key=gemini_api_key)
                self._llm = genai.GenerativeModel("gemini-2.5-flash")
                logger.info("Initialized Gemini 2.5 Flash for WhatsApp natural language parsing.")
            except Exception as e:
                logger.warning("Could not initialize Gemini LLM for message understanding: %s", e)

    def parse_deterministic(
        self,
        text: str,
        payload_id: Optional[str] = None,
        current_state: Optional[ConversationState] = None,
        current_draft: Optional[TripDraft] = None,
    ) -> ExtractedTripSlots:
        """
        Instant, robust deterministic parsing.
        Leverages current conversation state so single-word answers (e.g., 'Chennai', '2')
        are seamlessly mapped without friction.
        """
        slots = ExtractedTripSlots()
        clean_text = text.strip()
        lower = clean_text.lower()

        # 1. Confirmation / Affirmation Intent
        if (
            payload_id == "btn_confirm"
            or lower in (
                "yes", "confirm", "proceed", "looks good", "generate", "plan it",
                "go ahead", "yes take it", "take it", "sure", "ok", "okay",
                "fine", "yeah", "yep", "do it"
            )
            or re.match(r"^(?:yes|sure|ok|okay|yep|yeah)\b", lower)
        ):
            slots.confirmation_intent = True
            if not any(k in lower for k in ("from", "to", "days", "trip")):
                return slots

        # 2. Reset / Start Over Intent
        if payload_id == "btn_cancel" or lower in ("reset", "restart", "start over", "cancel", "new trip", "clear", "abort"):
            slots.reset_intent = True
            slots.confirmation_intent = False
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
            elif payload_id == "btn_travelers_1":
                slots.travelers = 1
            elif payload_id == "btn_travelers_2":
                slots.travelers = 2
            elif payload_id == "btn_travelers_4":
                slots.travelers = 4

        # 4. Direct "from <Origin> to <Destination>" Pattern (Highest precedence)
        from_to_match = re.search(
            r"\bfrom\s+([A-Za-z\s]+?)\s+to\s+([A-Za-z\s]+?)(?:\s+on|\s+for|\s+with|\s+in|$)",
            clean_text,
            re.IGNORECASE
        )
        if from_to_match:
            slots.origin = from_to_match.group(1).strip().title()
            slots.destination = from_to_match.group(2).strip().title()

        # 5. Multi-Slot Travel Intent: "Plan a trip to <Dest> for <X> days from <Origin>"
        if not slots.destination or not slots.origin:
            trip_match = re.search(
                r"\b(?:plan|book|need|want)?\s*(?:a\s+)?(?:trip|travel|tour|vacation)?\s*(?:to|visit|visiting)\s+([A-Za-z\s]+?)\s+(?:for\s+(\d+)\s*(?:days?|nights?))?(?:\s+from\s+([A-Za-z\s]+?))?(?:\s+on|\s+with|\s+in|$)",
                clean_text,
                re.IGNORECASE
            )
            if trip_match:
                d_cand = trip_match.group(1).strip()
                dur_cand = trip_match.group(2)
                o_cand = trip_match.group(3)
                if d_cand and len(d_cand) >= 2 and d_cand.lower() not in ("a trip", "trip", "vacation"):
                    slots.destination = d_cand.title()
                if dur_cand and not slots.duration_days:
                    slots.duration_days = int(dur_cand)
                if o_cand and not slots.origin:
                    o_cand = re.sub(r"^(?:from|starting)\s+", "", o_cand, flags=re.IGNORECASE).strip()
                    if o_cand:
                        slots.origin = o_cand.title()

        if not slots.origin:
            from_match = re.search(r"\bfrom\s+([A-Za-z\s]+?)(?:\s+to|\s+on|\s+for|\s+with|\s+in|$)", clean_text, re.IGNORECASE)
            if from_match:
                slots.origin = from_match.group(1).strip().title()

        if not slots.destination:
            to_match = re.search(r"\b(?:to|trip to|visiting|visit)\s+([A-Za-z\s]+?)(?:\s+from|\s+on|\s+for|\s+with|\s+in|$)", clean_text, re.IGNORECASE)
            if to_match:
                dest_cand = to_match.group(1).strip()
                if len(dest_cand) >= 3 and dest_cand.lower() not in ("chennai", "delhi", "mumbai", "train", "bus", "flight"):
                    slots.destination = dest_cand.title()

        # 6. Natural Language & Regex Date Parsing
        s_date, e_date, dur = self._parse_dates_nlp(clean_text)
        if s_date:
            slots.start_date = s_date
        if e_date:
            slots.end_date = e_date
        if dur:
            slots.duration_days = dur

        # 7. Travelers Count
        travelers_match = re.search(r"\b(\d{1,2})\s+(?:people|persons?|travelers?|adults?|passengers?|friends?)\b", lower)
        if travelers_match:
            slots.travelers = min(max(int(travelers_match.group(1)), 1), 20)
        elif current_state == ConversationState.COLLECT_TRAVELERS:
            digits_only = re.search(r"^\s*(\d{1,2})\s*$", clean_text)
            if digits_only:
                slots.travelers = min(max(int(digits_only.group(1)), 1), 20)
        if not slots.travelers:
            if re.search(r"\b(solo|myself|alone|just me)\b", lower):
                slots.travelers = 1
            elif re.search(r"\b(couple|two of us|me and my (wife|husband|partner|friend))\b", lower):
                slots.travelers = 2
            elif re.search(r"\b(family of 3|three of us)\b", lower):
                slots.travelers = 3
            elif re.search(r"\b(family of 4|four of us)\b", lower):
                slots.travelers = 4

        # 8. Transport Mode Mapping
        if not slots.transport_mode:
            if re.search(r"\b(train|railway|irctc|express)\b", lower):
                slots.transport_mode = TransportPref.train
            elif re.search(r"\b(bus|redbus|coach|sleeper)\b", lower):
                slots.transport_mode = TransportPref.bus
            elif re.search(r"\b(flight|fly|plane|air|airline)\b", lower):
                slots.transport_mode = TransportPref.flight
            elif re.search(r"\b(any transport|any mode|any)\b", lower) and current_state == ConversationState.COLLECT_TRANSPORT:
                slots.transport_mode = TransportPref.any

        # 9. Budget Level Mapping
        if not slots.budget_level:
            if re.search(r"\b(low budget|cheap|budget friendly|economy|low)\b", lower):
                slots.budget_level = BudgetLevel.low
            elif re.search(r"\b(medium budget|mid[- ]?range|moderate|medium|standard)\b", lower):
                slots.budget_level = BudgetLevel.medium
            elif re.search(r"\b(luxury|high budget|expensive|premium|5[- ]?star|high)\b", lower):
                slots.budget_level = BudgetLevel.high

        # 10. Hotel Category Mapping
        if not slots.hotel_category:
            if re.search(r"\b(budget hotel|hostel|dorm|cheap hotel|budget)\b", lower):
                slots.hotel_category = HotelPref.budget
            elif re.search(r"\b(mid[- ]?range hotel|3[- ]?star|mid[- ]?range|standard)\b", lower):
                slots.hotel_category = HotelPref.mid_range
            elif re.search(r"\b(luxury hotel|resort|4[- ]?star|5[- ]?star|luxury)\b", lower):
                slots.hotel_category = HotelPref.luxury

        # 11. State-Aware Contextual Mapping (Single-word / direct reply support)
        if current_state:
            # When bot asked "Which city will you be traveling from?"
            if current_state == ConversationState.COLLECT_ORIGIN and not slots.origin:
                city_cand = re.sub(r"^(?:from|starting from|i am at|i am in)\s+", "", clean_text, flags=re.IGNORECASE).strip()
                if len(city_cand) >= 2 and not any(k in city_cand.lower() for k in ("yes", "no", "hi", "reset", "plan")):
                    slots.origin = city_cand.title()

            # When bot asked "Where is your dream destination?"
            elif current_state in (ConversationState.START, ConversationState.COLLECT_DESTINATION) and not slots.destination:
                city_cand = re.sub(r"^(?:to|trip to|visit|visiting|going to)\s+", "", clean_text, flags=re.IGNORECASE).strip()
                if len(city_cand) >= 2 and not any(k in city_cand.lower() for k in ("yes", "no", "hi", "reset", "plan")):
                    slots.destination = city_cand.title()

            # When bot asked "How many people are traveling?"
            elif current_state == ConversationState.COLLECT_TRAVELERS and not slots.travelers:
                digits = re.search(r"^\s*(\d{1,2})\s*$", clean_text)
                if digits:
                    slots.travelers = min(max(int(digits.group(1)), 1), 20)

            # When bot asked for dates and user provided only days
            elif current_state == ConversationState.COLLECT_DATES:
                if not slots.start_date and not slots.duration_days:
                    days_only = re.search(r"^\s*(\d{1,2})\s*(?:days?|nights?)?\s*$", clean_text, re.IGNORECASE)
                    if days_only:
                        slots.duration_days = int(days_only.group(1))

        return slots

    def _parse_dates_nlp(self, text: str) -> Tuple[Optional[date], Optional[date], Optional[int]]:
        """
        Extracts start date, end date, and duration from diverse natural expressions.
        """
        lower = text.lower().strip()
        year = date.today().year

        # Pattern 1: Month Name Ranges (e.g., "October 10 - 16", "Oct 10 to 16", "October 10 to October 16")
        m1 = re.search(
            r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})\s*(?:-|to)\s*(?:(?:(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+)?(\d{1,2}))\b",
            lower
        )
        if m1:
            try:
                mon1_str, d1_str, mon2_str, d2_str = m1.group(1), int(m1.group(2)), m1.group(3), int(m1.group(4))
                m1_val = MONTH_NAMES[mon1_str]
                m2_val = MONTH_NAMES[mon2_str] if mon2_str else m1_val
                # If date is in past this year, roll to next year
                calc_year = year
                s_date = date(calc_year, m1_val, d1_str)
                if s_date < date.today():
                    calc_year += 1
                    s_date = date(calc_year, m1_val, d1_str)
                e_date = date(calc_year, m2_val, d2_str)
                dur = max(1, (e_date - s_date).days)
                return s_date, e_date, dur
            except (ValueError, KeyError):
                pass

        # Pattern 2: "From Month Day for X days" (e.g., "From October 7 for 4 days", "Oct 7 for 3 nights")
        m2 = re.search(
            r"\b(?:from\s+)?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})\s+(?:for\s+)?(\d+)\s*(?:days?|nights?)\b",
            lower
        )
        if m2:
            try:
                mon_str, d_str, dur_val = m2.group(1), int(m2.group(2)), int(m2.group(3))
                m_val = MONTH_NAMES[mon_str]
                calc_year = year
                s_date = date(calc_year, m_val, d_str)
                if s_date < date.today():
                    calc_year += 1
                    s_date = date(calc_year, m_val, d_str)
                e_date = s_date + timedelta(days=dur_val)
                return s_date, e_date, dur_val
            except (ValueError, KeyError):
                pass

        # Pattern 3: Two explicit dates separated by to/- (e.g., "15-10-2026 to 19-10-2026")
        m3_dmy = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\s*(?:to|-)\s*(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", lower)
        if m3_dmy:
            try:
                d1, mo1, y1, d2, mo2, y2 = map(int, m3_dmy.groups())
                s_date = date(y1, mo1, d1)
                e_date = date(y2, mo2, d2)
                dur = max(1, (e_date - s_date).days)
                return s_date, e_date, dur
            except ValueError:
                pass

        m3_iso = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s*(?:to|-)\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", lower)
        if m3_iso:
            try:
                y1, mo1, d1, y2, mo2, d2 = map(int, m3_iso.groups())
                s_date = date(y1, mo1, d1)
                e_date = date(y2, mo2, d2)
                dur = max(1, (e_date - s_date).days)
                return s_date, e_date, dur
            except ValueError:
                pass

        # Pattern 4: Relative dates ("tomorrow", "this weekend", "next friday", etc.)
        today = date.today()
        if "tomorrow" in lower:
            s_date = today + timedelta(days=1)
            dur_m = re.search(r"(\d+)\s*(?:days?|nights?)", lower)
            dur = int(dur_m.group(1)) if dur_m else 3
            return s_date, s_date + timedelta(days=dur), dur

        if "weekend" in lower:
            days_ahead = (4 - today.weekday()) % 7  # Friday
            if days_ahead == 0 and "next" in lower:
                days_ahead = 7
            elif "next" in lower:
                days_ahead += 7
            s_date = today + timedelta(days=days_ahead)
            return s_date, s_date + timedelta(days=3), 3

        if "next week" in lower:
            days_ahead = (7 - today.weekday()) % 7 or 7  # Next Monday
            s_date = today + timedelta(days=days_ahead)
            return s_date, s_date + timedelta(days=4), 4

        # Pattern 5: Single Date + Duration (e.g., "2026-10-15 for 4 days" or "15-10-2026 for 4 days")
        dur_match = re.search(r"\b(?:for\s+)?(\d+)\s*(?:days?|nights?)\b", lower)
        dur = int(dur_match.group(1)) if dur_match else None

        date_iso = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", lower)
        date_dmy = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", lower)

        s_date = None
        if date_iso:
            try:
                y, mo, d = map(int, date_iso.groups())
                s_date = date(y, mo, d)
            except ValueError:
                pass
        elif date_dmy:
            try:
                d, mo, y = map(int, date_dmy.groups())
                s_date = date(y, mo, d)
            except ValueError:
                pass

        if s_date:
            dur = dur or 3
            return s_date, s_date + timedelta(days=dur), dur

        if dur:
            # Only duration provided (e.g., "for 4 days"): Pick next Friday
            days_ahead = (4 - today.weekday()) % 7
            if days_ahead < 2:
                days_ahead += 7
            s_date = today + timedelta(days=days_ahead)
            return s_date, s_date + timedelta(days=dur), dur

        return None, None, None

    async def parse(
        self,
        text: str,
        payload_id: Optional[str] = None,
        current_state: Optional[ConversationState] = None,
        current_draft: Optional[TripDraft] = None,
    ) -> ExtractedTripSlots:
        """
        Parses user input using fast deterministic rules first.
        Falls back to Gemini 2.5 Flash structured JSON extraction for unstructured free-text.
        """
        slots = self.parse_deterministic(
            text=text,
            payload_id=payload_id,
            current_state=current_state,
            current_draft=current_draft,
        )
        if slots.has_slots() or slots.confirmation_intent is not None or slots.reset_intent:
            return slots

        # If deterministic rules didn't catch slots on multi-word free text, invoke Gemini 2.5 Flash
        if self._llm and len(text.strip().split()) >= 2:
            try:
                llm_slots = await self._parse_with_llm(text, current_state)
                if llm_slots.has_slots():
                    return llm_slots
            except Exception as e:
                logger.warning("LLM extraction failed: %s. Using deterministic slots.", e)

        return slots

    async def _parse_with_llm(self, text: str, current_state: Optional[ConversationState] = None) -> ExtractedTripSlots:
        """Structured Gemini 2.5 Flash JSON extraction for complex travel phrases."""
        prompt = f"""
        You are a travel assistant extracting travel slots from user WhatsApp messages.
        Current context/question being answered: {current_state.value if current_state else 'General'}
        User message: "{text}"

        Output ONLY a valid JSON object with these keys (null if missing):
        {{
            "origin": "string city or null",
            "destination": "string city or null",
            "start_date": "YYYY-MM-DD or null",
            "end_date": "YYYY-MM-DD or null",
            "duration_days": integer or null,
            "travelers": integer or null,
            "budget_level": "low" | "medium" | "high" | null,
            "transport_mode": "train" | "bus" | "flight" | "any" | null,
            "hotel_category": "budget" | "mid_range" | "luxury" | null,
            "interests": []
        }}
        """
        response = await self._llm.generate_content_async(prompt)
        raw_text = response.text.strip()
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text)
        data = json.loads(raw_text)
        return ExtractedTripSlots.model_validate(data)


message_parser = MessageParser()
