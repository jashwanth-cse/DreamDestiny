import asyncio

from app.orchestration.trip_orchestrator import TripOrchestrator


def test_empty_hotel_result_is_retried_instead_of_cached():
    class Hotels:
        calls = 0
        async def get_hotels(self, *_args, **_kwargs):
            self.calls += 1
            return [] if self.calls == 1 else ["recovered hotel"]
    async def run():
        hotels = Hotels()
        orchestrator = TripOrchestrator(tourism=object(), hotels=hotels,
            buses=object(), trains=object(), route=object())
        assert await orchestrator._get_hotels("Kochi", "2026-12-15", "2026-12-17", 1, 0) == []
        assert await orchestrator._get_hotels("Kochi", "2026-12-15", "2026-12-17", 1, 0) == ["recovered hotel"]
        assert hotels.calls == 2
    asyncio.run(run())
