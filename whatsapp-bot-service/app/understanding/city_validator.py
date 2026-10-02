"""
City & Destination Validator.
Prevents arbitrary or irrelevant inputs (e.g., 'Check If It Works', 'asdfghjk', 'hello')
from being accepted as destinations or origin cities.
"""

import re
import logging
from typing import Tuple, Optional

from app.config import settings

logger = logging.getLogger(__name__)



# Curated set of common Indian travel hubs, cities, and tourist spots for instant O(1) matching
KNOWN_CITIES = {
    "mumbai", "delhi", "bengaluru", "bangalore", "hyderabad", "chennai", "kolkata", "pune",
    "ahmedabad", "jaipur", "surat", "lucknow", "kanpur", "nagpur", "indore", "thane",
    "bhopal", "visakhapatnam", "patna", "vadodara", "ghaziabad", "ludhiana", "agra", "nashik",
    "faridabad", "meerut", "rajkot", "varanasi", "srinagar", "aurangabad", "dhanbad", "amritsar",
    "navi mumbai", "allahabad", "prayagraj", "howrah", "ranchi", "gwalior", "jabalpur", "coimbatore",
    "vijayawada", "jodhpur", "madurai", "raipur", "kota", "chandigarh", "guwahati", "solapur",
    "hubli", "mysore", "mysuru", "tiruchirappalli", "bareilly", "aligarh", "tiruppur", "gurgaon",
    "gurugram", "moradabad", "jalandhar", "bhubaneswar", "salem", "warangal", "mira bhayandar",
    "jalgaon", "guntur", "thiruvananthapuram", "trivandrum", "bhiwandi", "saharanpur", "gorakhpur",
    "bikaner", "amravati", "noida", "jamshedpur", "bhilai", "cuttack", "firozabad", "kochi",
    "cochin", "nellore", "bhavnagar", "dehradun", "durgapur", "asansol", "rourkela", "nanded",
    "kolhapur", "ajmer", "akola", "gulbarga", "jamnagar", "ujjain", "loni", "siliguri", "jhansi",
    "ulhasnagar", "jammu", "sangli", "mangalore", "erode", "belgaum", "ambattur", "tirunelveli",
    "malegaon", "gaya", "jalna", "udaipur", "maheshtala", "davanagere", "kozhikode", "calicut",
    "kurnool", "rajpur sonarpur", "rajahmundry", "bokaro", "south dumdum", "bellary", "patiala",
    "gopalpur", "agartala", "bhagalpur", "muzaffarnagar", "bhatpara", "panihati", "latur",
    "dhule", "rohtak", "korba", "bhilwara", "berhampur", "muzaffarpur", "ahmednagar", "mathura",
    "kollam", "avadi", "kadapa", "kamarhati", "sambalpur", "bilaspur", "shahjahanpur", "satara",
    "bijapur", "ramagundam", "shimoga", "chandrapur", "junagadh", "thrissur", "alwar", "bardhaman",
    "kulti", "kakinada", "nizamabad", "parbhani", "tumkur", "khammam", "ozhukarai", "bihar sharif",
    "panipat", "darbhanga", "bally", "aizawl", "dewas", "ichalkaranji", "karnal", "bathinda",
    "jalpaiguri", "eluru", "kirari suleman nagar", "barasat", "purnia", "satna", "mau", "sonipat",
    "farrukhabad", "sagar", "rourkela", "durg", "imphal", "ratlam", "hapur", "arrah", "karimnagar",
    "anantapur", "etawah", "ambernath", "north dumdum", "bharatpur", "begusarai", "new delhi",
    "gandhidham", "baranagar", "tiruvottiyur", "pondicherry", "puducherry", "sikar", "thoothukudi",
    "tuticorin", "rewa", "mirzapur", "raichur", "pali", "rampur", "haridwar", "vijayanagaram",
    "katihar", "nagarcoil", "sri ganganagar", "karawal nagar", "mango", "thanjavur", "bulandshahr",
    "uluberia", "murwara", "sambhal", "singrauli", "nadiad", "secunderabad", "naihati", "yamunanagar",
    "bidhan nagar", "pallavaram", "bidar", "munger", "panchcula", "burhanpur", "raiganj",
    "kharagpur", "dindigul", "gandhinagar", "hospet", "nangloi jat", "malda", "ongole", "deoghar",
    "chapra", "haldia", "khandwa", "nandyal", "chittoor", "morena", "amroha", "anand", "bhind",
    "bhalswa jahangir pur", "madhyamgram", "bhiwani", "navi mumbai panvel", "bahraich",
    "rajapalayam", "srivilliputhur", "tenkasi", "sivakasi", "virudhunagar", "kovilpatti", "ooty",
    "kodaikanal", "munnar", "alleppey", "alappuzha", "wayanad", "varkala", "hampi", "gokarna",
    "coorg", "madikeri", "dandeli", "chikmagalur", "badami", "manali", "shimla", "dharamshala",
    "mcleodganj", "dalhousie", "kullu", "kasol", "spiti", "leh", "ladakh", "rishikesh", "nainital",
    "mussoorie", "auli", "jim corbett", "chopta", "lansdowne", "ranikhet", "almora", "mount abu",
    "pushkar", "jaisalmer", "ranthambore", "chittorgarh", "mandawa", "bundi", "khajuraho", "orchha",
    "pachmarhi", "kanha", "bandhavgarh", "pench", "darjeeling", "gangtok", "pelling", "kalimpong",
    "shillong", "cherrapunji", "tawang", "kaziranga", "digha", "mandarmani", "puri", "konark",
    "goa", "north goa", "south goa", "panaji", "calangute", "baga", "anjuna", "candolim", "palolem",
    "rameswaram", "kanyakumari", "mahabalipuram", "yercaud", "yelagiri", "valparai", "courtallam",
    "tirupati", "araku", "vizag", "horsley hills", "andaman", "port blair", "havelock", "lakshadweep"
}

# Strict blacklist of phrases that are NEVER cities
BLOCKED_PHRASES = {
    "check if it works", "testing", "test", "hello", "hi", "hey", "what is this", "tell me",
    "ok", "okay", "yes", "no", "asdf", "qwerty", "nothing", "none", "random", "why", "how",
    "who", "where", "can you", "please", "thanks", "thank you", "plan a trip", "trip", "tour",
    "vacation", "holiday", "good morning", "good evening", "bye", "start", "restart", "help"
}


class CityValidator:
    def __init__(self, bedrock_api_key: Optional[str] = settings.bedrock_api_key):
        self._llm = None
        if genai and bedrock_api_key:
            try:
                genai.configure(api_key=bedrock_api_key)
                self._llm = genai.GenerativeModel("gemini-2.5-flash")
            except Exception as e:
                logger.warning("Could not initialize Gemini for city validation: %s", e)

    async def validate_city(self, candidate: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validates if candidate is a genuine city or travel destination.
        Returns (is_valid, normalized_name, suggested_name).
        """
        if not candidate:
            return False, None, None

        clean = re.sub(r"^(?:to|from|visit|visiting|trip to|starting from)\s+", "", candidate.strip(), flags=re.IGNORECASE)
        clean = clean.strip(" .,!?-")
        lower = clean.lower()

        # 1. Blocked phrases check
        if lower in BLOCKED_PHRASES or len(clean) < 2 or clean.isdigit():
            return False, None, None

        # 2. Known Indian & world destinations instant check
        if lower in KNOWN_CITIES:
            return True, clean.title(), None

        # 3. Google Maps Places API Check
        if settings.google_maps_api_key:
            import httpx
            try:
                url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
                params = {
                    "input": clean,
                    "types": "(cities)",
                    "key": settings.google_maps_api_key
                }
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(url, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("status") == "OK" and data.get("predictions"):
                            main_text = data["predictions"][0].get("structured_formatting", {}).get("main_text", "")
                            # If it's a direct match
                            if main_text.lower() == lower:
                                return True, main_text, None
                            # If it's close, it might be a typo
                            # We will still pass it to Gemini for typo confirmation to be safe
            except Exception as e:
                logger.warning("Google Places API check failed: %s", e)

        # 4. LLM Oracle check for typos and unlisted cities
        if self._llm:
            try:
                import json
                prompt = (
                    f"The user entered '{clean}' as a travel destination. "
                    f"Is this a real geographic city/destination? "
                    f"If it has a spelling mistake (e.g. 'gao' instead of 'Goa', 'mumbay' for 'Mumbai'), what is the correct spelling? "
                    f"Respond ONLY with valid JSON: {{\"is_valid\": bool, \"corrected_name\": \"string or null\"}}"
                )
                from app.understanding.llm_router import global_llm_router
                res = await global_llm_router.generate_content_async(prompt)
                raw = res.text.strip()
                if raw.startswith("```"):
                    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
                
                data = json.loads(raw)
                is_valid = data.get("is_valid", False)
                corrected = data.get("corrected_name")
                
                if is_valid and (not corrected or corrected.lower() == lower):
                    return True, clean.title(), None
                if corrected and corrected.lower() != lower:
                    return False, None, corrected
                return False, None, None
            except Exception as e:
                logger.warning("Gemini place verification failed: %s. Falling back to length check.", e)
                words = clean.split()
                if 1 <= len(words) <= 3 and all(w.isalpha() for w in words):
                    return True, clean.title(), None

        # Fallback if no LLM: accept alpha strings of 3-30 chars not in blacklist
        if 3 <= len(clean) <= 30 and all(w.isalpha() for w in clean.split()):
            return True, clean.title(), None

        return False, None, None


city_validator = CityValidator()
