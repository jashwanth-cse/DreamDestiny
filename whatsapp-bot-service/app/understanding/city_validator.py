"""
City & Destination Validator.
Prevents arbitrary or irrelevant inputs (e.g., 'Check If It Works', 'asdfghjk', 'hello')
from being accepted as destinations or origin cities.
Supports common Indian railway codes and city abbreviations (e.g. RJPM -> Rajapalayam).
"""

import sys
import re
import opcode
import logging
from typing import Tuple, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class CityValidationResult:
    """
    Smart result object that safely supports both 2-unpack and 3-unpack:
      is_valid, name = await city_validator.validate_city(...)
      is_valid, norm, sugg = await city_validator.validate_city(...)
    """
    def __init__(self, is_valid: bool, name: Optional[str] = None, suggestion: Optional[str] = None):
        self.is_valid = bool(is_valid)
        self.name = name
        self.suggestion = suggestion
        self._items = (self.is_valid, self.name, self.suggestion)

    def __iter__(self):
        try:
            f = sys._getframe(1)
            code = f.f_code.co_code
            i = f.f_lasti
            unpack_op = opcode.opmap.get("UNPACK_SEQUENCE", 92)
            count = 3
            for offset in range(0, 10, 2):
                if i + offset < len(code) and code[i + offset] == unpack_op:
                    count = code[i + offset + 1]
                    break
            if count == 2:
                return iter(self._items[:2])
        except Exception:
            pass
        return iter(self._items)

    def __getitem__(self, index):
        return self._items[index]

    def __len__(self):
        return 3

    def __repr__(self):
        return f"CityValidationResult(is_valid={self.is_valid}, name={self.name!r}, suggestion={self.suggestion!r})"


# Common Indian Railway station codes and conversational city abbreviations
CITY_ALIASES = {
    # Tamil Nadu / South India
    "rjpm": "Rajapalayam",
    "mdu": "Madurai",
    "cbe": "Coimbatore",
    "mas": "Chennai",
    "ms": "Chennai",
    "tbm": "Chennai",
    "tpj": "Tiruchirappalli",
    "trichy": "Tiruchirappalli",
    "tly": "Thalassery",
    "tcr": "Thrissur",
    "ers": "Kochi",
    "cochin": "Kochi",
    "tvm": "Thiruvananthapuram",
    "trivandrum": "Thiruvananthapuram",
    "sbc": "Bangalore",
    "blr": "Bangalore",
    "bengaluru": "Bangalore",
    "mys": "Mysore",
    "mysuru": "Mysore",
    "ubl": "Hubli",
    "ixm": "Madurai",
    "vpt": "Virudhunagar",
    "svpr": "Srivilliputhur",
    "tsi": "Tenkasi",
    "kcvl": "Trivandrum",
    # North / West / East
    "csmt": "Mumbai",
    "bct": "Mumbai",
    "bom": "Mumbai",
    "del": "Delhi",
    "ndls": "Delhi",
    "dli": "Delhi",
    "hwh": "Kolkata",
    "sda": "Kolkata",
    "ccu": "Kolkata",
    "calcutta": "Kolkata",
    "hyd": "Hyderabad",
    "secunderabad": "Hyderabad",
    "sc": "Hyderabad",
    "pnq": "Pune",
    "goa": "Goa",
    "mao": "Goa",
    "jpr": "Jaipur",
    "vns": "Varanasi",
    "bsb": "Varanasi",
    "lko": "Lucknow",
    "adi": "Ahmedabad",
    "amd": "Ahmedabad",
    "ixc": "Chandigarh",
    "pat": "Patna",
    "bhu": "Bhubaneswar",
    "bbs": "Bhubaneswar",
    "vizag": "Visakhapatnam",
}

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
    "farrukhabad", "sagar", "durg", "imphal", "ratlam", "hapur", "arrah", "karimnagar",
    "anantapur", "etawah", "ambernath", "north dumdum", "bharatpur", "begusarai", "new delhi",
    "gandhidham", "baranagar", "tiruvottiyur", "pondicherry", "puducherry", "sikar", "thoothukudi",
    "tuticorin", "rewa", "mirzapur", "raichur", "pali", "rampur", "haridwar", "vijayanagaram",
    "katihar", "nagarcoil", "sri ganganagar", "karawal nagar", "mango", "thanjavur", "bulandshahr",
    "uluberia", "murwara", "sambhal", "singrauli", "nadiad", "secunderabad", "naihati", "yamunanagar",
    "bidhan nagar", "pallavaram", "bidar", "munger", "panchkula", "burhanpur", "raiganj",
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
    "vacation", "holiday", "good morning", "good evening", "bye", "start", "restart", "help",
    "exit", "cancel", "quit", "stop", "end", "own car", "car", "flight", "train", "bus"
}


class CityValidator:
    def __init__(self):
        pass

    async def validate_city(self, candidate: str) -> CityValidationResult:
        """
        Validates if candidate is a genuine city or travel destination.
        Returns CityValidationResult which can be unpacked as 2 or 3 values:
          is_valid, normalized_name, suggested_name
        """
        if not candidate:
            return CityValidationResult(False, None, None)

        # Clean conversational prefixes like "I want to go to", "visit", "trip to"
        clean = re.sub(
            r"^(?:i\s+(?:want|wish|would\s+like|went|plan|am\s+planning)\s+to\s+(?:go\s+to|visit|travel\s+to|reach)?|"
            r"plan\s+(?:a\s+)?trip\s+to|trip\s+to|going\s+to|go\s+to|travel\s+to|visit|visiting|head\s+to|take\s+me\s+to|"
            r"starting\s+from|traveling\s+from|from|to)\s+",
            "",
            candidate.strip(),
            flags=re.IGNORECASE,
        )
        clean = clean.strip(" .,!?-")
        lower = clean.lower()

        # 1. Blocked phrases check
        if lower in BLOCKED_PHRASES or len(clean) < 2 or clean.isdigit():
            return CityValidationResult(False, None, None)

        # 2. Station code & alias expansion (e.g. RJPM -> Rajapalayam)
        if lower in CITY_ALIASES:
            expanded = CITY_ALIASES[lower]
            return CityValidationResult(True, expanded, None)

        # 3. Known Indian & world destinations instant check
        if lower in KNOWN_CITIES:
            return CityValidationResult(True, clean.title(), None)

        # 4. Google Maps Places API Check (if configured)
        if settings.google_maps_api_key:
            import httpx
            try:
                url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
                params = {
                    "input": clean,
                    "types": "(cities)",
                    "key": settings.google_maps_api_key,
                }
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(url, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("status") == "OK" and data.get("predictions"):
                            main_text = data["predictions"][0].get("structured_formatting", {}).get("main_text", "")
                            if main_text.lower() == lower:
                                return CityValidationResult(True, main_text, None)
            except Exception as e:
                logger.warning("Google Places API check failed: %s", e)

        # 5. LLM Oracle check for typos and unlisted cities
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
            raw = getattr(res, "text", str(res)).strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)

            data = json.loads(raw)
            is_valid = data.get("is_valid", False)
            corrected = data.get("corrected_name")

            if is_valid and (not corrected or corrected.lower() == lower):
                return CityValidationResult(True, clean.title(), None)
            if corrected and corrected.lower() != lower:
                return CityValidationResult(False, None, corrected)
            return CityValidationResult(False, None, None)
        except Exception as e:
            logger.warning("Bedrock place verification failed: %s. Falling back to word check.", e)
            words = clean.split()
            if 1 <= len(words) <= 3 and all(w.isalpha() for w in words):
                return CityValidationResult(True, clean.title(), None)

        # Fallback if no LLM: accept alpha strings of 3-30 chars not in blacklist
        if 3 <= len(clean) <= 30 and all(w.isalpha() for w in clean.split()):
            return CityValidationResult(True, clean.title(), None)

        return CityValidationResult(False, None, None)


city_validator = CityValidator()
