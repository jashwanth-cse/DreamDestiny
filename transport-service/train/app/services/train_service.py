"""
Train Search Service

Responsible for resolving station names to codes, querying the Ixigo API,
and parsing the raw JSON response into a clean, strictly typed structure.
"""

import re
import requests
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Any, Tuple

from app.config import config
from app.services.station_service import StationService
from app.services.availability_service import AvailabilityService

logger = logging.getLogger(__name__)

# Global session for connection pooling
_session = requests.Session()

# Shared availability service singleton
_availability_service = AvailabilityService()

# Max concurrent live availability requests per search call
_MAX_CONCURRENT_AVAILABILITY = 5

class TrainService:
    """
    Service class to handle train searches between two stations.
    Stateless and thread-safe.
    """

    def __init__(self) -> None:
        self.url = config.TRAIN_API
        self.headers = config.TRAIN_HEADERS
        self.station_service = StationService()

    def _build_params(self, source_code: str, dest_code: str, journey_date: str) -> Dict[str, str]:
        """Builds query parameters for the Ixigo API request."""
        return {
            "sourceStationCode": source_code,
            "destinationStationCode": dest_code,
            "addAvailabilityCache": "true",
            "excludeMultiTicketAlternates": "false",
            "excludeBoostAlternates": "false",
            "sortBy": "DEFAULT",
            "dateOfJourney": journey_date,
            "enableNearby": "true",
            "enableTG": "true",
            "tGPlan": "ITG-A50",
            "showTGPrediction": "false",
            "tgColor": "DEFAULT",
            "showPredictionGlobal": "true",
            "showNewAlternates": "true",
            "showNewAltText": "true"
        }

    def _call_ixigo(self, params: Dict[str, str]) -> Dict[str, Any]:
        """Makes the HTTP request to the Ixigo API."""
        try:
            response = _session.get(
                self.url,
                params=params,
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            raise Exception("Ixigo API Timeout")
        except requests.exceptions.ConnectionError:
            raise Exception("Unable to connect to Ixigo")
        except requests.exceptions.HTTPError as e:
            raise Exception(f"HTTP Error : {e}")
        except Exception as e:
            raise Exception(f"Unknown Error : {e}")

    # --------------------------------------------------------
    # Search & Parse
    # --------------------------------------------------------

    @staticmethod
    def _normalize_journey_date(raw_date: str) -> str:
        """
        Normalizes any date string (YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY, YYYY/MM/DD)
        into the required DD-MM-YYYY format for the Ixigo API.
        """
        raw = str(raw_date).strip()
        if not raw:
            return ""
        # YYYY-MM-DD -> DD-MM-YYYY
        if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
            parts = raw.split("-")
            return f"{parts[2]}-{parts[1]}-{parts[0]}"
        # YYYY/MM/DD -> DD-MM-YYYY
        if re.match(r"^\d{4}/\d{2}/\d{2}$", raw):
            parts = raw.split("/")
            return f"{parts[2]}-{parts[1]}-{parts[0]}"
        # DD/MM/YYYY -> DD-MM-YYYY
        if re.match(r"^\d{2}/\d{2}/\d{4}$", raw):
            parts = raw.split("/")
            return f"{parts[0]}-{parts[1]}-{parts[2]}"
        return raw

    def search(
        self,
        source: str,
        destination: str,
        journey_date: str,
        travel_class: Optional[str] = None,
        sort_by: str = "departure",
        max_fare: Optional[int] = None,
        min_rating: Optional[float] = None,
        pantry: Optional[bool] = None,
        quota: str = "GN",
    ) -> Dict[str, Any]:
        """
        Main entry point to search for trains.
        """
        # Normalize date to DD-MM-YYYY format for the provider API
        date_str = self._normalize_journey_date(journey_date)

        # ── Step 0: Resolve stations concurrently (instant for cached/pre-seeded) ──
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_src = executor.submit(self.station_service.get_station, source)
            future_dst = executor.submit(self.station_service.get_station, destination)
            source_station = future_src.result()
            dest_station = future_dst.result()

        params = self._build_params(source_station["station_code"], dest_station["station_code"], date_str)
        raw_data = self._call_ixigo(params)
        
        payload = raw_data.get("data", {})
        trains_data = payload.get("trainList", [])
        result_type = "direct"

        if not trains_data:
            trains_data = payload.get("nearbyTrains", [])
            result_type = "nearby"

        # ── Step 1: Parse all trains ───────────────────────────────────────────
        parsed_trains = []
        for train in trains_data:
            parsed_trains.append(self._parse_train(train, source_station, dest_station))

        # ── Step 2: Enrich missing availability (concurrent, before filtering) ─
        # Determine the classes that will survive class-filtering so we only
        # fetch live availability for classes the user will actually see.
        target_class = travel_class.upper() if travel_class else None
        self._enrich_availability(parsed_trains, date_str, quota, target_class)

        # ── Step 3: Filter, recommend, sort ───────────────────────────────────
        result_trains = []
        for parsed_train in parsed_trains:
            # Filter classes
            parsed_train["classes"] = self._filter_classes(parsed_train["classes"], travel_class)

            # Re-evaluate lowest fare and recommendation after filtering
            parsed_train["recommended_class"] = self._recommend_class(parsed_train["classes"])
            parsed_train["lowest_fare"] = self._calculate_lowest_fare(parsed_train["classes"])

            # Apply optional filters
            if max_fare is not None and parsed_train["lowest_fare"] > max_fare:
                continue
            if min_rating is not None and parsed_train["rating"] < min_rating:
                continue
            if pantry is not None and parsed_train["has_pantry"] != pantry:
                continue

            # Only include trains that still have matching classes after filter
            if parsed_train["classes"]:
                result_trains.append(parsed_train)

        # Sort trains
        result_trains = self._sort_trains(result_trains, sort_by)

        return {
            "result_type": result_type,
            "source": payload.get("sourceStationName") or source_station["station_name"],
            "destination": payload.get("destinationStationName") or dest_station["station_name"],
            "total_trains": len(result_trains),
            "trains": result_trains,
        }

    # --------------------------------------------------------
    # Private Parsing Helpers
    # --------------------------------------------------------

    def _parse_train(self, train: Dict[str, Any], source_station: Dict[str, str], dest_station: Dict[str, str]) -> Dict[str, Any]:
        """Extracts desired fields from a raw train object."""
        classes = self._parse_classes(train)
        
        from_code = train.get("fromStnCode", "")
        to_code = train.get("toStnCode", "")
        
        # If the train departs/arrives exactly at the queried station, use the resolved name.
        from_name = source_station["station_name"] if from_code == source_station["station_code"] else train.get("fromStnName", from_code)
        to_name = dest_station["station_name"] if to_code == dest_station["station_code"] else train.get("toStnName", to_code)
        
        duration_mins = train.get("duration", 0)

        return {
            "train_number": train.get("trainNumber", ""),
            "train_name": train.get("trainName", ""),
            "train_type": train.get("trainType", ""),
            "from": {
                "code": from_code,
                "name": from_name
            },
            "to": {
                "code": to_code,
                "name": to_name
            },
            "departure_time": train.get("departureTime", ""),
            "arrival_time": train.get("arrivalTime", ""),
            "duration_minutes": duration_mins,
            "duration": self._minutes_to_duration(duration_mins),
            "distance": train.get("distance", 0),
            "running_days": self._parse_running_days(train.get("runningDays", "")),
            "rating": train.get("trainRating", 0),
            "has_pantry": bool(train.get("hasPantry")),
            "lowest_fare": self._calculate_lowest_fare(classes),
            "recommended_class": self._recommend_class(classes) or {},
            "classes": classes
        }

    def _parse_classes(self, train: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parses the availabilityCache into a list of standardized class objects."""
        availability = train.get("availabilityCache", {})
        parsed = []
        for class_name, details in availability.items():
            parsed.append(self._parse_class(class_name, details))
        return parsed

    def _parse_class(self, class_name: str, details: Dict[str, Any]) -> Dict[str, Any]:
        """Parses an individual class detail object."""
        fare = int(details.get("fare") or 0)
        availability = details.get("availabilityDisplayName") or details.get("availability") or ""
        prediction = details.get("predictionPercentage") or 0
        
        is_bookable = "REGRET" not in str(availability).upper()

        # Tag whether this class has real cached availability
        has_availability = bool(str(availability).strip())

        return {
            "travel_class": class_name,
            "fare": fare,
            "availability": availability,
            "prediction": prediction,
            "bookable": is_bookable,
            "availability_source": "cached" if has_availability else "pending",
        }

    # --------------------------------------------------------
    # Live Availability Enrichment
    # --------------------------------------------------------

    @staticmethod
    def _needs_enrichment(cls: Dict[str, Any]) -> bool:
        """Return True if this class is missing availability and needs a live fetch."""
        return not str(cls.get("availability", "")).strip()

    def _enrich_availability(
        self,
        parsed_trains: List[Dict[str, Any]],
        journey_date: str,
        quota: str,
        target_class: Optional[str],
    ) -> None:
        """
        Enriches classes that have empty availability by calling the live
        availability API concurrently (up to _MAX_CONCURRENT_AVAILABILITY workers).

        Rules:
        - Only fetches for classes with blank/null availability.
        - Skips classes that won't survive class-filter (target_class filter).
        - Uses train["from"]["code"] and train["to"]["code"] as station codes.
        - Deduplicates identical (train_no, src, dst, cls, date, quota) combos.
        - A single failure never aborts the whole search.
        - Updates classes in-place.
        """
        # Build the work list: (train_idx, class_idx, key_tuple)
        work: List[Tuple[int, int, Tuple]] = []
        seen_keys = set()

        for t_idx, train in enumerate(parsed_trains):
            train_no = train["train_number"]
            src_code = train["from"]["code"]
            dst_code = train["to"]["code"]

            for c_idx, cls in enumerate(train["classes"]):
                class_name = cls["travel_class"]

                # Skip if class won't survive filter
                if target_class and class_name != target_class:
                    continue

                # Skip if availability is already present
                if not self._needs_enrichment(cls):
                    cls["availability_source"] = "cached"
                    continue

                key = (train_no, src_code, dst_code, class_name, journey_date, quota)
                if key in seen_keys:
                    # Will be filled by the canonical entry; mark as pending
                    continue
                seen_keys.add(key)
                work.append((t_idx, c_idx, key))

        if not work:
            return

        logger.info(
            f"TrainService: enriching availability for {len(work)} class(es) concurrently "
            f"(max={_MAX_CONCURRENT_AVAILABILITY} workers)"
        )

        # Maps key → live result for dedup sharing
        results: Dict[Tuple, Dict[str, Any]] = {}

        def fetch(key: Tuple) -> Tuple[Tuple, Dict[str, Any]]:
            train_no, src, dst, cls_name, date, q = key
            result = _availability_service.fetch_availability(
                train_no=train_no,
                source=src,
                destination=dst,
                travel_class=cls_name,
                date=date,
                quota=q,
            )
            return key, result

        with ThreadPoolExecutor(max_workers=_MAX_CONCURRENT_AVAILABILITY) as executor:
            futures = {executor.submit(fetch, item[2]): item for item in work}
            for future in as_completed(futures):
                try:
                    key, result = future.result()
                    results[key] = result
                except Exception as exc:
                    key = futures[future][2]
                    logger.warning(f"Live availability fetch failed for {key}: {exc}")
                    results[key] = {"success": False, "data": None}

        # Apply results back to classes (including dedup sharing)
        for train in parsed_trains:
            train_no = train["train_number"]
            src_code = train["from"]["code"]
            dst_code = train["to"]["code"]

            for cls in train["classes"]:
                class_name = cls["travel_class"]
                if target_class and class_name != target_class:
                    continue
                if not self._needs_enrichment(cls):
                    continue  # Already tagged "cached" above

                key = (train_no, src_code, dst_code, class_name, journey_date, quota)
                result = results.get(key)
                self._apply_live_result(cls, result)

    @staticmethod
    def _apply_live_result(cls: Dict[str, Any], result: Optional[Dict[str, Any]]) -> None:
        """
        Apply a live availability result to a class dict.
        Preserves the existing fare from the search response — does NOT overwrite it.
        Sets availability_source to "live" on success, "unavailable" on failure.
        """
        if not result or not result.get("success") or not result.get("data"):
            cls["availability_source"] = "unavailable"
            cls["bookable"] = False
            return

        data = result["data"]
        live_avail = str(data.get("availability") or "").strip()

        if not live_avail:
            cls["availability_source"] = "unavailable"
            cls["bookable"] = False
            return

        cls["availability"]        = live_avail
        cls["prediction"]          = int(data.get("prediction") or 0)
        cls["bookable"]            = bool(data.get("booking_enabled", True))
        cls["availability_source"] = "live"

        # Re-evaluate bookable from availability string as a safety net
        if "REGRET" in live_avail.upper():
            cls["bookable"] = False



    @staticmethod
    def _calculate_lowest_fare(classes: List[Dict[str, Any]]) -> int:
        fares = [c["fare"] for c in classes if c["fare"] > 0]
        return min(fares) if fares else 0

    @staticmethod
    def _minutes_to_duration(minutes: int) -> str:
        if not minutes:
            return "0h 0m"
        hrs = minutes // 60
        mins = minutes % 60
        return f"{hrs}h {mins}m"

    @staticmethod
    def _parse_running_days(days: str) -> List[str]:
        names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        if not days or len(days) != 7:
            return []
        return [names[i] for i, val in enumerate(days) if val == "1"]

    @staticmethod
    def _recommend_class(classes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Recommendations priority:
        1. AVAILABLE / AVL
        2. RAC
        3. Highest prediction percentage
        Never recommend REGRET.
        """
        if not classes:
            return None
            
        valid_classes = [c for c in classes if "REGRET" not in str(c.get("availability", "")).upper()]
        if not valid_classes:
            return None
            
        avl_classes = [
            c for c in valid_classes 
            if "AVL" in str(c.get("availability", "")).upper() 
            or "AVAILABLE" in str(c.get("availability", "")).upper()
        ]
        if avl_classes:
            return min(avl_classes, key=lambda x: x.get("fare", float('inf')))
            
        rac_classes = [
            c for c in valid_classes 
            if "RAC" in str(c.get("availability", "")).upper()
        ]
        if rac_classes:
            return min(rac_classes, key=lambda x: x.get("fare", float('inf')))
            
        return max(valid_classes, key=lambda x: (x.get("prediction", 0), -x.get("fare", 0)))

    @staticmethod
    def _filter_classes(classes: List[Dict[str, Any]], travel_class: Optional[str]) -> List[Dict[str, Any]]:
        if not travel_class:
            return classes
        travel_class = travel_class.upper()
        return [c for c in classes if c.get("travel_class") == travel_class]

    @staticmethod
    def _sort_trains(trains: List[Dict[str, Any]], sort_by: str) -> List[Dict[str, Any]]:
        sort_by = sort_by.lower()
        if sort_by == "departure":
            return sorted(trains, key=lambda x: x.get("departure_time", ""))
        elif sort_by == "arrival":
            return sorted(trains, key=lambda x: x.get("arrival_time", ""))
        elif sort_by == "duration":
            return sorted(trains, key=lambda x: x.get("duration_minutes", float('inf')))
        elif sort_by == "fare":
            return sorted(trains, key=lambda x: x.get("lowest_fare", float('inf')))
        return trains