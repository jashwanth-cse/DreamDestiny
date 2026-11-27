import asyncio

import httpx

from app.clients.hotel_routes import HotelRoutesClient


def test_routes_matrix_maps_out_of_order_rows_and_ignores_unreachable(monkeypatch):
    async def run():
        rows = [{"originIndex": 1, "destinationIndex": 0, "condition": "ROUTE_EXISTS",
                 "distanceMeters": 3500, "duration": "721s"},
                {"originIndex": 0, "destinationIndex": 0, "condition": "ROUTE_NOT_FOUND"},
                {"originIndex": 0, "destinationIndex": 1, "condition": "ROUTE_EXISTS",
                 "distanceMeters": 2000, "duration": "360s"}]
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json=rows)
        original = httpx.AsyncClient
        def client_factory(*_args, **_kwargs):
            return original(transport=httpx.MockTransport(handler))
        monkeypatch.setattr("app.clients.hotel_routes.httpx.AsyncClient", client_factory)
        result = await HotelRoutesClient("test-key").matrix(
            [(17.4, 78.4), (17.5, 78.5)], [(17.6, 78.6), (17.7, 78.7)])
        assert result[(1, 0)].minutes == 13
        assert result[(0, 1)].minutes == 6
        assert (0, 0) not in result
        assert len(requests) == 1
    asyncio.run(run())
