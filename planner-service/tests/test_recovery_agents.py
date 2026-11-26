import asyncio
from datetime import date, datetime, timezone

from app.recovery.models import RecoveryRequest, Commitment
from app.recovery.service import RecoveryService
from app.schemas.context import TripContext, BusContext, AttractionContext
from app.schemas.request import TripRequest


class FakeOrchestrator:
    async def build_context(self, trip):
        return TripContext(
            trip=trip,
            outbound_buses=[BusContext(operator_name="Verified Bus", bus_type="AC Sleeper",
                                       departure_time="19:30", arrival_time="01:30",
                                       minimum_fare=950, available_seats=4)],
            attractions=[AttractionContext(name="City Museum", address="Main Road"),
                         AttractionContext(name="Lake Park", address="Lake Road")],
        )


class SelectingModel:
    def __init__(self):
        self.calls = []

    async def generate_json(self, system_prompt, user_data, json_schema):
        self.calls.append(system_prompt)
        return {"ids": [user_data["candidates"][0]["id"], "invented:option"]}


def test_two_agents_use_independent_tools_and_reject_invented_ids():
    async def run():
        llm = SelectingModel()
        trip = TripRequest(origin="Chennai", destination="Madurai",
                           start_date=date(2026, 12, 1), end_date=date(2026, 12, 3))
        service = RecoveryService(FakeOrchestrator(), llm,
                                  now=lambda: datetime(2026, 11, 26, tzinfo=timezone.utc))
        request = RecoveryRequest(trip=trip, change="My train was delayed by 2 hours",
                                  commitments=[Commitment(id="train1", kind="transport", title="Train 123",
                                      starts_at="2026-12-01T09:00:00+05:30",
                                      ends_at="2026-12-01T15:00:00+05:30", confirmed=True),
                                      Commitment(id="tour1", kind="activity", title="Museum tour",
                                      starts_at="2026-12-01T16:00:00+05:30", confirmed=True)])
        result = await service.recover(request)
        assert result.status == "ready"
        assert len(llm.calls) == 2
        assert [t.agent for t in result.traces] == ["mobility", "experience"]
        assert [t.tools for t in result.traces] == [["mobility_options"], ["experience_options"]]
        assert "tour1" in result.affected_commitment_ids
        assert all(o.id != "invented:option" for o in result.options)
        assert result.options[0].price == 950

    asyncio.run(run())


def test_unknown_change_asks_clarification_without_provider_call():
    async def run():
        trip = TripRequest(origin="Chennai", destination="Madurai",
                           start_date=date(2026, 12, 1), end_date=date(2026, 12, 3))
        class BrokenOrchestrator:
            async def build_context(self, trip):
                raise AssertionError("Provider should not be called")
        service = RecoveryService(BrokenOrchestrator(), SelectingModel())
        result = await service.recover(RecoveryRequest(trip=trip, change="I need some help here"))
        assert result.status == "needs_clarification"
    asyncio.run(run())
