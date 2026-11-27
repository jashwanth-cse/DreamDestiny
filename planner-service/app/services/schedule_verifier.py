"""Ground sightseeing times in Google Routes and published Places hours."""

from __future__ import annotations

from datetime import date, datetime

from app.clients.hotel_routes import HotelRoutesClient
from app.schemas.context import AttractionContext, TripContext
from app.schemas.itinerary import Itinerary


def _minutes(value: str | None) -> int | None:
    if not value:
        return None
    for fmt in ("%H:%M", "%I:%M %p"):
        try:
            parsed = datetime.strptime(value.strip(), fmt)
            return parsed.hour * 60 + parsed.minute
        except (TypeError, ValueError):
            pass
    return None


def _periods(hours: dict | None, day: date) -> list[tuple[int, int]] | None:
    if not isinstance(hours, dict) or not isinstance(hours.get("periods"), list):
        return None
    weekday = (day.weekday() + 1) % 7  # Google: Sunday=0.
    result = []
    for period in hours["periods"]:
        opened, closed = period.get("open") or {}, period.get("close") or {}
        if opened.get("day") != weekday:
            continue
        start = _minutes(f"{opened.get('hour', 0):02}:{opened.get('minute', 0):02}")
        end = _minutes(f"{closed.get('hour', 0):02}:{closed.get('minute', 0):02}") if closed else 1440
        if start is not None and end is not None and end > start:
            result.append((start, end))
    return sorted(result)


def _note(itinerary: Itinerary, message: str) -> None:
    itinerary.planning_notes = ((itinerary.planning_notes or "").strip() + " " + message).strip()


class ScheduleVerifier:
    def __init__(self, routes: HotelRoutesClient | None = None):
        self.routes = routes or HotelRoutesClient()

    async def apply(self, itinerary: Itinerary, context: TripContext) -> Itinerary:
        places = {item.name.casefold(): item for item in context.attractions}
        interests = {interest.casefold() for interest in context.trip.preferences.activities.interests}
        has_museum = any(
                "museum" in activity.attraction_name.casefold()
                for day in itinerary.days for activity in day.activities)
        if "museums" in interests and not has_museum:
            candidates = [place for place in context.attractions
                          if "museum" in place.name.casefold() and place.business_status not in
                          {"CLOSED_TEMPORARILY", "CLOSED_PERMANENTLY"}]
            if candidates and itinerary.days:
                target = max(itinerary.days, key=lambda day: (len(day.activities), day.date or ""))
                if target.activities:
                    museum = max(candidates, key=lambda place: (place.rating or 0, place.review_count))
                    # A museum's daytime hours make an early slot safer than
                    # replacing the final late-afternoon attraction.
                    displaced = target.activities[0]
                    displaced.attraction_name = museum.name
                    displaced.notes = None
                    displaced.estimated_cost = None
        seen = set()
        for day in itinerary.days:
            try:
                calendar_day = date.fromisoformat(day.date or "")
            except ValueError:
                continue
            if "museums" in interests:
                museum_visit = next((activity for activity in day.activities
                                     if "museum" in activity.attraction_name.casefold()
                                     and activity.attraction_name.casefold() in places
                                     and _periods(places[activity.attraction_name.casefold()].opening_hours,
                                                  calendar_day)), None)
                if museum_visit is not None:
                    day.activities.remove(museum_visit)
                    museum_visit.start_time = "09:00"
                    day.activities.insert(0, museum_visit)
            selected: list[tuple[object, AttractionContext]] = []
            for activity in day.activities:
                place = places.get(activity.attraction_name.casefold())
                if place is None or activity.attraction_name.casefold() in seen:
                    _note(itinerary, f"Omitted unverified or duplicate visit: {activity.attraction_name}.")
                    continue
                seen.add(activity.attraction_name.casefold())
                if place.business_status in {"CLOSED_TEMPORARILY", "CLOSED_PERMANENTLY"}:
                    _note(itinerary, f"Omitted closed place: {activity.attraction_name}.")
                    continue
                selected.append((activity, place))
            coords = [(p.latitude, p.longitude) for _, p in selected]
            route = {}
            if len(coords) > 1 and len(coords) ** 2 <= 200 and all(
                    lat is not None and lng is not None for lat, lng in coords):
                route = await self.routes.matrix(coords, coords)
            kept = []
            previous_index = None
            previous_end = None
            arrival = itinerary.outbound_transport
            arrival_floor = None
            if arrival and arrival.arrival_date == day.date:
                arrival_clock = _minutes(arrival.arrival_time)
                if arrival_clock is not None:
                    # Before hotel selection, allow for the arrival transfer and check-in.
                    arrival_floor = arrival_clock + (120 if arrival.mode == "flight" else 90)
            elif arrival and arrival.arrival_date and arrival.arrival_date > day.date:
                arrival_floor = 1440
            for index, (activity, place) in enumerate(selected):
                requested = _minutes(activity.start_time)
                if requested is None:
                    requested = 9 * 60
                duration = activity.duration_minutes or 60
                duration = max(45, min(duration, 240))
                earliest = requested
                if arrival_floor is not None:
                    earliest = max(earliest, arrival_floor)
                if previous_end is not None:
                    road = route.get((previous_index, index))
                    travel = road.minutes if road else 45
                    earliest = max(earliest, previous_end + travel + 10)
                    if road is None:
                        _note(itinerary, f"Route to {activity.attraction_name} could not be verified; allow at least 45 minutes for transfer.")
                intervals = _periods(place.opening_hours, calendar_day)
                if intervals is None:
                    _note(itinerary, f"Confirm opening hours for {activity.attraction_name} before visiting.")
                    start, actual_duration = earliest, duration
                else:
                    possible = [(max(earliest, opening), min(duration, closing - max(earliest, opening)))
                                for opening, closing in intervals]
                    feasible = [(start, length) for start, length in possible if length >= 45]
                    if not feasible:
                        _note(itinerary, f"Omitted {activity.attraction_name}: no time remains within published opening hours.")
                        continue
                    start, actual_duration = max(feasible, key=lambda item: (item[1], -item[0]))
                    if actual_duration < duration:
                        _note(itinerary, f"Shortened {activity.attraction_name} to fit published opening hours.")
                if start + actual_duration > 1440:
                    _note(itinerary, f"Omitted {activity.attraction_name}: insufficient time today.")
                    continue
                activity.start_time = f"{start // 60:02}:{start % 60:02}"
                activity.duration_minutes = actual_duration
                kept.append(activity)
                previous_index, previous_end = index, start + actual_duration
            day.activities = kept
        return itinerary
