"""Choose a sourced hotel near the actual planned sights and describe the arrival transfer."""

from __future__ import annotations

from math import asin, cos, isfinite, radians, sin, sqrt
import re
from statistics import mean
from urllib.parse import urlencode

from app.clients.hotel_routes import HotelRoutesClient, RoadRoute
from app.schemas.context import AttractionContext, HotelContext, TripContext
from app.schemas.itinerary import ArrivalToHotel, HotelDecision, Itinerary


def _point(item) -> tuple[float, float] | None:
    lat, lon = item.latitude, item.longitude
    if (lat is None or lon is None or not (isfinite(lat) and isfinite(lon)) or
            not (-90 <= lat <= 90 and -180 <= lon <= 180) or
            (lat == 0 and lon == 0)):
        return None
    return float(lat), float(lon)


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
    value = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(value))


def _review_rating(hotel: HotelContext) -> float:
    count = max(0, hotel.review_count or 0)
    rating = min(5.0, max(0.0, hotel.rating or 0.0))
    return (40 * 3.8 + count * rating) / (40 + count)


def _budget_ceiling(context: TripContext) -> float | None:
    budget = context.trip.preferences.budget.level.value
    category = context.trip.preferences.hotel.category.value
    limits = {"low": 1500.0, "medium": 5000.0, "high": None}
    ceiling = limits[budget]
    category_ceiling = {"budget": 1500.0, "mid_range": 5000.0,
                        "luxury": None, "any": None}[category]
    if category_ceiling is not None:
        ceiling = min(ceiling, category_ceiling) if ceiling is not None else category_ceiling
    return ceiling


def _planned_attractions(context: TripContext, itinerary: Itinerary) -> list[AttractionContext]:
    by_name = {a.name.casefold().strip(): a for a in context.attractions if _point(a)}
    selected = []
    seen = set()
    for day in itinerary.days:
        for activity in day.activities:
            name = activity.attraction_name.casefold().strip()
            attraction = by_name.get(name)
            if attraction and name not in seen:
                selected.append(attraction)
                seen.add(name)
    if selected:
        return selected[:20]
    return sorted(by_name.values(), key=lambda a: (-(a.rating or 0), -a.review_count))[:12]


def _arrival_stop(context: TripContext, itinerary: Itinerary) -> str | None:
    decision = itinerary.outbound_transport
    if not decision or decision.mode not in {"train", "bus", "flight"}:
        return None
    if decision.mode == "train" and decision.train_number:
        train = next((t for t in context.outbound_trains
                      if t.train_number == decision.train_number), None)
        if train and train.to_station_name:
            return train.to_station_name
    if decision.mode == "bus" and decision.operator_name:
        buses = [b for b in context.outbound_buses
                 if b.operator_name == decision.operator_name and b.dropping_point]
        if len(buses) == 1:
            return buses[0].dropping_point
        arrival_time = re.search(r"\b\d{1,2}:\d{2}\b", decision.arrival_time or "")
        if arrival_time:
            matching = [b for b in buses if arrival_time.group() in (b.arrival_time or "")]
            if len(matching) == 1:
                return matching[0].dropping_point
    stop = (decision.arrival_station or "").strip()
    if stop.casefold() in {"", context.trip.destination.casefold(),
                           f"{context.trip.destination.casefold()} city"}:
        return None
    return stop


class HotelRecommendationService:
    def __init__(self, routes: HotelRoutesClient | None = None):
        self.routes = routes or HotelRoutesClient()

    async def apply(self, itinerary: Itinerary, context: TripContext) -> Itinerary:
        # The model may omit a hotel or invent one. Only SerpApi candidates can survive.
        hotels = [h for h in context.hotels if h.id and h.name and
                  h.price.currency == "INR" and
                  (h.price.per_night is None or h.price.per_night > 0)]
        if not hotels:
            itinerary.hotel = None
            itinerary.arrival_to_hotel = None
            return itinerary
        priced = [h for h in hotels if h.price.per_night is not None]
        if priced:
            hotels = priced
        ceiling = _budget_ceiling(context)
        within = [h for h in hotels if ceiling is None or
                  (h.price.per_night is not None and h.price.per_night <= ceiling)]
        budget_exceeded = not within and ceiling is not None
        if within:
            hotels = within
        attractions = _planned_attractions(context, itinerary)
        points = [_point(a) for a in attractions]
        points = [p for p in points if p is not None]
        def preliminary(hotel: HotelContext):
            point = _point(hotel)
            straight = mean(_km(point, a) for a in points) if point and points else 9999
            return (straight, -_review_rating(hotel), hotel.price.per_night or float("inf"))
        # Bound paid matrix elements while retaining cheap, reviewed and central candidates.
        ranked_preliminary = sorted(hotels, key=preliminary)
        candidates = ranked_preliminary[:8]
        for extra in (min(hotels, key=lambda h: h.price.per_night or float("inf")),
                      max(hotels, key=_review_rating)):
            if all(existing.id != extra.id for existing in candidates) and len(candidates) < 10:
                candidates.append(extra)
        candidates = list({hotel.id: hotel for hotel in candidates}.values())
        route_hotels = [h for h in candidates if _point(h)]
        matrix: dict[tuple[int, int], RoadRoute] = {}
        if route_hotels and points:
            matrix = await self.routes.matrix([_point(h) for h in route_hotels], points)
        scored = []
        for index, hotel in enumerate(route_hotels):
            times = [matrix.get((index, j)) for j in range(len(points))]
            if not times or any(route is None for route in times):
                continue
            minutes = [route.minutes for route in times]
            average, worst = mean(minutes), max(minutes)
            # All planned sights have equal weight. Penalize one distant sight,
            # then adjust for review confidence and nightly cost.
            price = hotel.price.per_night or 0
            price_penalty = (8 * price / ceiling) if ceiling else min(8, price / 1000)
            score = average + 0.8 * (worst - average) + 10 * (5 - _review_rating(hotel)) + price_penalty
            scored.append((score, hotel.id, hotel, average, worst))
        if scored:
            _, _, selected, average, worst = min(scored)
        else:
            selected = min(candidates, key=lambda h: (-_review_rating(h),
                                                      h.price.per_night or float("inf"), h.id))
            average = worst = None
        price = selected.price.per_night
        rationale = (f"Rated {selected.rating:.1f}/5 from {selected.review_count} reviews; "
                     if selected.rating is not None and selected.review_count else
                     "SerpApi hotel search result; ")
        if average is not None:
            rationale += (f"about {round(average)} min average and {worst} min worst drive "
                          f"to {len(points)} planned sights. Road estimates; traffic varies.")
        else:
            rationale += "road travel times to planned sights could not be verified."
        if budget_exceeded:
            rationale += " Above your selected nightly budget target; review before booking."
        itinerary.hotel = HotelDecision(
            hotel_id=selected.id, hotel_name=selected.name, reasoning=rationale,
            price_per_night=price, price_total=selected.price.total,
            rating=selected.rating, review_count=selected.review_count,
            avg_attraction_drive_minutes=round(average) if average is not None else None,
            furthest_attraction_drive_minutes=worst)
        itinerary.arrival_to_hotel = await self._arrival_transfer(context, itinerary, selected)
        return itinerary

    async def _arrival_transfer(self, context: TripContext, itinerary: Itinerary,
                                hotel: HotelContext) -> ArrivalToHotel | None:
        decision = itinerary.outbound_transport
        if not decision or decision.mode not in {"train", "bus", "flight"}:
            return None
        stop = _arrival_stop(context, itinerary)
        if not stop:
            return ArrivalToHotel(from_name="Your arrival stop", to_hotel=hotel.name,
                instruction="Confirm your exact arrival station or bus drop point, then take a taxi or auto to the hotel.")
        point = _point(hotel)
        if point is None:
            return ArrivalToHotel(from_name=stop, to_hotel=hotel.name,
                instruction="Take a taxi or auto from this arrival point; confirm the route in Maps.")
        params = urlencode({"api": "1", "origin": f"{stop}, {context.trip.destination}, India",
                            "destination": f"{point[0]},{point[1]}", "travelmode": "driving"})
        link = f"https://www.google.com/maps/dir/?{params}"
        origin = await self.routes.geocode_stop(stop, context.trip.destination)
        route = None
        if origin is not None and _km(origin, point) <= 100:
            route = (await self.routes.matrix([origin], [point])).get((0, 0))
        instruction = (f"Take a taxi or auto from {stop} to {hotel.name}; "
                       f"about {route.minutes} min by road ({route.distance_km} km). Traffic varies."
                       if route else f"Take a taxi or auto from {stop} to {hotel.name}; check live travel time in Maps.")
        return ArrivalToHotel(from_name=stop, to_hotel=hotel.name,
            mode="road", travel_minutes=route.minutes if route else None,
            distance_km=route.distance_km if route else None,
            maps_url=link, instruction=instruction)
