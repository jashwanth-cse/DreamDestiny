"""
Context & Topic Guardrail Shield for WhatsApp Bot.
Enforces strict conversational boundaries for a production travel assistant:
- Permits all travel, tourism, vacation, itinerary, transit, accommodation, and bot navigation queries.
- Strictly flags off-topic queries (coding, politics, homework, trivia, medical/legal, recipes, general AI tasks)
  so they can be dropped or politely deflected according to production safety policy.
"""

import re
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# In-scope navigation and travel regex patterns
NAVIGATION_PATTERNS = re.compile(
    r"^(hi|hello|hey|greetings|hola|namaste|vanakkam|good\s*(morning|afternoon|evening)|"
    r"menu|main\s*menu|options|help|reset|cancel|start\s*over|new\s*trip|plan\s*trip|"
    r"yes|no|ok|okay|fine|sure|confirm|proceed|continue|resume|past\s*trips|my\s*trips|"
    r"trip\s*\d+|view\s*trip|\d+)$",
    re.IGNORECASE,
)

TRAVEL_KEYWORDS = {
    "trip", "travel", "tour", "tourist", "tourism", "vacation", "holiday", "itinerary",
    "journey", "visit", "explore", "flight", "flights", "plane", "airline", "train", "railway",
    "irctc", "bus", "sleeper", "volvo", "cab", "taxi", "drive", "car", "hotel", "resort",
    "homestay", "hostel", "stay", "room", "budget", "luxury", "cheap", "cost", "price",
    "fare", "days", "nights", "weekend", "tomorrow", "places", "attractions", "sightseeing",
    "beach", "mountain", "hill", "temple", "monument", "food", "restaurant", "destination",
    "origin", "depart", "arrival", "ticket", "pack", "weather", "mumbai", "delhi", "goa",
    "bangalore", "chennai", "kolkata", "hyderabad", "jaipur", "kerala", "manali", "shimla",
    "ooty", "kodaikanal", "pondicherry", "agra", "varanasi", "ladakh", "darjeeling", "coorg",
}

# Explicitly off-topic patterns: coding, math equations, political/trivia essay prompts, medical
OFF_TOPIC_PATTERNS = [
    re.compile(r"\b(def\s+\w+|function\s*\(|class\s+\w+|import\s+\w+|console\.log|select\s+.*\s+from|<!DOCTYPE|<html)\b", re.IGNORECASE),
    re.compile(r"\b(write\s+(a\s+)?(code|script|program|essay|poem|story|song|article)|debug\s+my|fix\s+this\s+bug)\b", re.IGNORECASE),
    re.compile(r"\b(solve|calculate|equation|algebra|integral|derivative|\d+\s*[\+\*\/\^]\s*\d+)\b", re.IGNORECASE),
    re.compile(r"\b(who\s+is\s+the\s+(president|prime\s+minister|ceo|king|queen)|election|politics|parliament)\b", re.IGNORECASE),
    re.compile(r"\b(prescribe|medicine|symptoms\s+of|cure\s+for|medical\s+advice|legal\s+advice|stock\s+market|invest\s+in\s+crypto)\b", re.IGNORECASE),
    re.compile(r"\b(recipe\s+for|how\s+to\s+bake|ingredients\s+for|quantum\s+physics|theory\s+of\s+relativity)\b", re.IGNORECASE),
]


class GuardrailShield:
    def __init__(self):
        pass

    async def is_in_scope(self, text: Optional[str], payload_id: Optional[str] = None) -> bool:
        """
        Determines whether the incoming user request is strictly in-scope for our Travel Concierge.
        Returns True if in-scope, False if off-topic.
        """
        # Interactive buttons are always in-scope
        if payload_id:
            return True

        if not text or not text.strip():
            return True

        clean = text.strip()
        lower = clean.lower()

        # 1. Check quick navigation whitelist (greetings, confirmations, commands)
        if NAVIGATION_PATTERNS.match(lower):
            return True

        # 2. Check explicit off-topic blacklists
        for pattern in OFF_TOPIC_PATTERNS:
            if pattern.search(clean):
                logger.info("[GUARDRAIL] Detected off-topic pattern in: '%s'", clean)
                return False

        # 3. Check for travel keywords / slot indicators
        words = set(re.findall(r"\b\w+\b", lower))
        if words.intersection(TRAVEL_KEYWORDS):
            return True

        # Check if text contains Indian city names
        from app.understanding.city_validator import KNOWN_CITIES
        for word in words:
            if word in KNOWN_CITIES:
                return True

        # Check for numbers / durations (e.g., "5", "3 days", "4 people", "15000")
        if re.search(r"\b\d+\b", lower) and len(words) <= 4:
            return True

        # 4. Short messages (<= 3 words) without off-topic flags are usually city names or answers
        if len(words) <= 3:
            return True

        # 5. For longer unstructured text, consult Bedrock oracle
        try:
            prompt = (
                "You are a strict domain guardrail for a WhatsApp AI Travel & Vacation Assistant named Dream Destiny.\n"
                f"User message: \"{clean}\"\n\n"
                "Determine if this message is relevant to travel, vacations, trips, geography, tourism, hotels, "
                "transportation, activities, budget, greetings, or conversational navigation.\n"
                "If the user asks about unrelated topics such as coding, math, general science, politics, "
                "cooking recipes, homework, or general trivia, it is OFF-TOPIC.\n"
                "Respond with exactly one word: IN_SCOPE or OFF_TOPIC."
            )
            from app.understanding.llm_router import global_llm_router
            response = await global_llm_router.generate_content_async(prompt)
            decision = response.upper()
            if "OFF_TOPIC" in decision:
                logger.info("[GUARDRAIL] LLM classified as OFF_TOPIC: '%s'", clean)
                return False
            return True
        except Exception as exc:
            logger.warning("[GUARDRAIL] LLM classification error: %s. Defaulting to in-scope.", exc)
            return True

        return True


guardrail_shield = GuardrailShield()
