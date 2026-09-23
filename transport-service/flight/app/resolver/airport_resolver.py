"""
Airport and City Code Resolver.

Maps city names, state capitals, and airport names to standard 3-letter IATA airport codes
required by SerpApi Google Flights API.

Examples:
    "Chennai"      → "MAA" (Chennai International Airport)
    "Coimbatore"   → "CJB" (Coimbatore International Airport)
    "Delhi"        → "DEL" (Indira Gandhi International Airport)
    "MAA"          → "MAA" (Direct 3-letter IATA passthrough)
"""

from typing import Dict, Tuple, Optional
from app.exceptions import AirportNotFoundError


# Comprehensive mapping of major Indian and global cities to (IATA_CODE, AIRPORT_NAME)
AIRPORT_DATABASE: Dict[str, Tuple[str, str]] = {
    # ── Tamil Nadu ────────────────────────────────────────────────────────────
    "chennai": ("MAA", "Chennai International Airport"),
    "madras": ("MAA", "Chennai International Airport"),
    "coimbatore": ("CJB", "Coimbatore International Airport"),
    "madurai": ("IXM", "Madurai Airport"),
    "trichy": ("TRZ", "Tiruchirappalli International Airport"),
    "tiruchirappalli": ("TRZ", "Tiruchirappalli International Airport"),
    "salem": ("SXV", "Salem Airport"),
    "tuticorin": ("TCR", "Tuticorin Airport"),
    "thoothukudi": ("TCR", "Tuticorin Airport"),
    "rajapalayam": ("IXM", "Madurai Airport (Nearest to Rajapalayam)"),
    "tirunelveli": ("TCR", "Tuticorin Airport (Nearest to Tirunelveli)"),
    "kanyakumari": ("TRV", "Trivandrum International Airport (Nearest to Kanyakumari)"),

    # ── Major Indian Metros ───────────────────────────────────────────────────
    "delhi": ("DEL", "Indira Gandhi International Airport"),
    "new delhi": ("DEL", "Indira Gandhi International Airport"),
    "mumbai": ("BOM", "Chhatrapati Shivaji Maharaj International Airport"),
    "bombay": ("BOM", "Chhatrapati Shivaji Maharaj International Airport"),
    "bangalore": ("BLR", "Kempegowda International Airport"),
    "bengaluru": ("BLR", "Kempegowda International Airport"),
    "kolkata": ("CCU", "Netaji Subhash Chandra Bose International Airport"),
    "calcutta": ("CCU", "Netaji Subhash Chandra Bose International Airport"),
    "hyderabad": ("HYD", "Rajiv Gandhi International Airport"),
    "secunderabad": ("HYD", "Rajiv Gandhi International Airport"),

    # ── Kerala & Karnataka ───────────────────────────────────────────────────
    "kochi": ("COK", "Cochin International Airport"),
    "cochin": ("COK", "Cochin International Airport"),
    "ernakulam": ("COK", "Cochin International Airport"),
    "trivandrum": ("TRV", "Thiruvananthapuram International Airport"),
    "thiruvananthapuram": ("TRV", "Thiruvananthapuram International Airport"),
    "calicut": ("CCJ", "Calicut International Airport"),
    "kozhikode": ("CCJ", "Calicut International Airport"),
    "kannur": ("CNN", "Kannur International Airport"),
    "mangalore": ("IXE", "Mangaluru International Airport"),
    "mangaluru": ("IXE", "Mangaluru International Airport"),
    "mysore": ("MYQ", "Mysuru Airport"),
    "mysuru": ("MYQ", "Mysuru Airport"),
    "hubli": ("HBX", "Hubballi Airport"),
    "belgaum": ("IXG", "Belagavi Airport"),

    # ── Andhra Pradesh & Telangana ───────────────────────────────────────────
    "visakhapatnam": ("VTZ", "Visakhapatnam Airport"),
    "vizag": ("VTZ", "Visakhapatnam Airport"),
    "vijayawada": ("VGA", "Vijayawada Airport"),
    "tirupati": ("TIR", "Tirupati Airport"),
    "rajahmundry": ("RJA", "Rajahmundry Airport"),
    "cuddapah": ("CDP", "Kadapa Airport"),
    "kadapa": ("CDP", "Kadapa Airport"),

    # ── West & Central India ─────────────────────────────────────────────────
    "goa": ("GOI", "Dabolim Airport"),
    "mopa": ("GOX", "Manohar International Airport"),
    "pune": ("PNQ", "Pune International Airport"),
    "ahmedabad": ("AMD", "Sardar Vallabhbhai Patel International Airport"),
    "surat": ("STV", "Surat Airport"),
    "vadodara": ("BDQ", "Vadodara Airport"),
    "baroda": ("BDQ", "Vadodara Airport"),
    "rajkot": ("RAJ", "Rajkot Airport"),
    "bhopal": ("BHO", "Raja Bhoj Airport"),
    "indore": ("IDR", "Devi Ahilyabai Holkar Airport"),
    "nagpur": ("NAG", "Dr. Babasaheb Ambedkar International Airport"),
    "jabalpur": ("JLR", "Jabalpur Airport"),
    "gwalior": ("GWL", "Gwalior Airport"),
    "aurangabad": ("IXU", "Chhatrapati Sambhajinagar Airport"),

    # ── North & East India ───────────────────────────────────────────────────
    "jaipur": ("JAI", "Jaipur International Airport"),
    "jodhpur": ("JDH", "Jodhpur Airport"),
    "udaipur": ("UDR", "Maharana Pratap Airport"),
    "lucknow": ("LKO", "Chaudhary Charan Singh International Airport"),
    "varanasi": ("VNS", "Lal Bahadur Shastri International Airport"),
    "agra": ("AGR", "Agra Airport"),
    "amritsar": ("ATQ", "Sri Guru Ram Dass Jee International Airport"),
    "chandigarh": ("IXC", "Shaheed Bhagat Singh International Airport"),
    "dehradun": ("DED", "Dehradun Airport"),
    "srinagar": ("SXR", "Sheikh ul-Alam International Airport"),
    "jammu": ("IXJ", "Jammu Airport"),
    "leh": ("IXL", "Kushok Bakula Rimpochee Airport"),
    "patna": ("PAT", "Jay Prakash Narayan Airport"),
    "ranchi": ("IXR", "Birsa Munda Airport"),
    "bhubaneswar": ("BBI", "Biju Patnaik International Airport"),
    "raipur": ("RPR", "Swami Vivekananda Airport"),
    "guwahati": ("GAU", "Lokpriya Gopinath Bordoloi International Airport"),
    "bagdogra": ("IXB", "Bagdogra International Airport"),
    "port blair": ("IXZ", "Veer Savarkar International Airport"),

    # ── Major International Hubs ─────────────────────────────────────────────
    "dubai": ("DXB", "Dubai International Airport"),
    "singapore": ("SIN", "Singapore Changi Airport"),
    "london": ("LHR", "London Heathrow Airport"),
    "bangkok": ("BKK", "Suvarnabhumi Airport"),
    "kuala lumpur": ("KUL", "Kuala Lumpur International Airport"),
    "doha": ("DOH", "Hamad International Airport"),
    "new york": ("JFK", "John F. Kennedy International Airport"),
    "san francisco": ("SFO", "San Francisco International Airport"),
    "paris": ("CDG", "Charles de Gaulle Airport"),
    "frankfurt": ("FRA", "Frankfurt Airport"),
    "tokyo": ("HND", "Tokyo Haneda Airport"),
}


class AirportResolver:
    """
    Resolves input strings (city name, state, airport title, or IATA code)
    into a validated 3-letter IATA code and official airport name.
    """

    @staticmethod
    def resolve(query: str) -> Tuple[str, str]:
        """
        Resolves query to (iata_code, airport_name).
        Raises AirportNotFoundError if query cannot be resolved.
        """
        cleaned = query.strip()
        if not cleaned:
            raise AirportNotFoundError("Origin or destination query cannot be empty")

        upper = cleaned.upper()

        # 1. Direct 3-letter uppercase IATA code check (e.g. 'MAA', 'DEL', 'JFK')
        if len(upper) == 3 and upper.isalpha():
            # Check if we have an official name for it
            for city, (code, name) in AIRPORT_DATABASE.items():
                if code == upper:
                    return code, name
            # Accept valid IATA format even if not in local database
            return upper, f"Airport ({upper})"

        # 2. Database lookup by normalized city/airport query
        normalized = cleaned.lower()
        if normalized in AIRPORT_DATABASE:
            return AIRPORT_DATABASE[normalized]

        # 3. Partial / substring match in database
        for city, (code, name) in AIRPORT_DATABASE.items():
            if city in normalized or normalized in city or normalized in name.lower():
                return code, name

        raise AirportNotFoundError(
            f"Could not resolve '{query}' to an airport code. "
            "Please provide a recognized city name or 3-letter IATA code (e.g. 'Chennai' or 'MAA')."
        )
