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

try:
    import google.generativeai as genai
except ImportError:
    genai = None

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
    def __init__(self, gemini_api_key: Optional[str] = settings.gemini_api_key):
        self._llm = None
        if genai and gemini_api_key:
            try:
                genai.configure(api_key=gemini_api_key)
                self._llm = genai.GenerativeModel("gemini-2.5-flash")
            except Exception as e:
                logger.warning("Could not initialize Gemini for city validation: %s", e)

    async def validate_city(self, candidate: str) -> Tuple[bool, Optional[str]]:
        """
        Validates if candidate is a genuine city or travel destination.
        Returns (is_valid, normalized_name).
        """
        if not candidate:
            return False, None

        clean = re.sub(r"^(?:to|from|visit|visiting|trip to|starting from)\s+", "", candidate.strip(), flags=re.IGNORECASE)
        clean = clean.strip(" .,!?-")
        lower = clean.lower()

        # 1. Blocked phrases check
        if lower in BLOCKED_PHRASES or len(clean) < 2 or clean.isdigit():
            return False, None

        # 2. Known Indian & world destinations instant check
        if lower in KNOWN_CITIES:
            return True, clean.title()

        # 3. LLM Oracle check for unlisted cities / towns
        if self._llm:
            try:
                prompt = (
                    f"Is '{clean}' a real geographical city, town, district, village, or travel destination "
                    f"in India or worldwide? Reply strictly YES or NO."
                )
                res = await self._llm.generate_content_async(prompt)
                ans = res.text.strip().upper()
                if "YES" in ans:
                    return True, clean.title()
                else:
                    return False, None
            except Exception as e:
                logger.warning("Gemini place verification failed: %s. Falling back to length check.", e)
                # If Gemini fails and text looks like a reasonable single/two word proper name, allow
                words = clean.split()
                if 1 <= len(words) <= 3 and all(w.isalpha() for w in words):
                    return True, clean.title()

        # Fallback if no LLM: accept alpha strings of 3-30 chars not in blacklist
        if 3 <= len(clean) <= 30 and all(w.isalpha() for w in clean.split()):
            return True, clean.title()

        return False, None


city_validator = CityValidator()
