import asyncio
import sys
from datetime import date

from app.clients.hotel_routes import RoadRoute
from app.schemas.context import AttractionContext, TripContext
from app.schemas.itinerary import Activity, DayPlan, Itinerary, ItinerarySummary, TransportDecision
from app.schemas.request import TripRequest
from app.services.schedule_verifier import ScheduleVerifier


class Routes:
    async def matrix(self, origins, destinations):
        return {(0, 1): RoadRoute(42, 12)}


def test_routes_and_opening_hours_adjust_sightseeing():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    trip = TripRequest(origin="Chennai", destination="Hyderabad",
                       start_date=date(2026, 12, 20), end_date=date(2026, 12, 22))
    # December 20, 2026 is Sunday, Google day 0.
    hours = {"periods": [{"open": {"day": 0, "hour": 10, "minute": 0},
                           "close": {"day": 0, "hour": 17, "minute": 0}}]}
    context = TripContext(trip=trip, attractions=[
        AttractionContext(name="Tombs", address="Hyderabad", latitude=17.4,
                          longitude=78.4, opening_hours=hours),
        AttractionContext(name="Palace", address="Hyderabad", latitude=17.5,
                          longitude=78.5, opening_hours=hours)])
    itinerary = Itinerary(summary=ItinerarySummary(origin="Chennai", destination="Hyderabad",
        days=2, travelers=1, pace="moderate", budget_level="medium"),
        days=[DayPlan(day=1, date="2026-12-20", activities=[
            Activity(attraction_name="Tombs", start_time="14:00", duration_minutes=60),
            Activity(attraction_name="Palace", start_time="16:00", duration_minutes=120)])])
    actual = asyncio.run(ScheduleVerifier(Routes()).apply(itinerary, context))
    activities = actual.days[0].activities
    assert len(activities) == 2
    assert activities[1].start_time == "16:00"
    assert activities[1].duration_minutes == 60


def test_arrival_day_does_not_schedule_before_train_reaches_city():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    trip = TripRequest(origin="Chennai", destination="Coimbatore",
                       start_date=date(2026, 12, 3), end_date=date(2026, 12, 4))
    hours = {"periods": [{"open": {"day": 4, "hour": 9},
                           "close": {"day": 4, "hour": 17}}]}
    context = TripContext(trip=trip, attractions=[AttractionContext(
        name="Gass Forest Museum", address="Coimbatore", opening_hours=hours)])
    itinerary = Itinerary(summary=ItinerarySummary(origin="Chennai", destination="Coimbatore",
        days=1, travelers=1, pace="relaxed", budget_level="low"),
        outbound_transport=TransportDecision(leg="outbound", mode="train",
            arrival_date="2026-12-03", arrival_time="14:05"),
        days=[DayPlan(day=1, date="2026-12-03", activities=[Activity(
            attraction_name="Gass Forest Museum", start_time="09:00", duration_minutes=120)])])
    actual = asyncio.run(ScheduleVerifier(Routes()).apply(itinerary, context))
    assert actual.days[0].activities[0].start_time == "15:35"
    assert actual.days[0].activities[0].duration_minutes == 85


def test_12_hour_arrival_time_and_museum_preference():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    trip = TripRequest(origin="Chennai", destination="Hyderabad",
        start_date=date(2026, 12, 20), end_date=date(2026, 12, 22),
        preferences={"activities": {"interests": ["museums"]}})
    context = TripContext(trip=trip, attractions=[
        AttractionContext(name="Hussain Sagar Lake", address="Hyderabad"),
        AttractionContext(name="Salar Jung Museum", address="Hyderabad",
            opening_hours={"periods": [{"open": {"day": 1, "hour": 10},
                                         "close": {"day": 1, "hour": 17}}]})])
    itinerary = Itinerary(summary=ItinerarySummary(origin="Chennai", destination="Hyderabad",
        days=2, travelers=1, pace="moderate", budget_level="high"),
        outbound_transport=TransportDecision(leg="outbound", mode="flight",
            arrival_date="2026-12-20", arrival_time="06:40 PM"),
        days=[DayPlan(day=1, date="2026-12-20", activities=[Activity(
            attraction_name="Hussain Sagar Lake", start_time="09:00", duration_minutes=60)]),
              DayPlan(day=2, date="2026-12-21", activities=[Activity(
                  attraction_name="Hussain Sagar Lake", start_time="09:00", duration_minutes=60),
                  Activity(attraction_name="Salar Jung Museum", start_time="17:00", duration_minutes=90)])])
    actual = asyncio.run(ScheduleVerifier(Routes()).apply(itinerary, context))
    names = [activity.attraction_name for day in actual.days for activity in day.activities]
    assert "Salar Jung Museum" in names
    assert actual.days[1].activities[0].start_time == "10:00"
    assert all(activity.start_time >= "20:40" for activity in actual.days[0].activities)
