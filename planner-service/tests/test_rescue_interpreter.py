import asyncio
import json
from datetime import date

import httpx

from app.config import settings
from app.recovery.interpreter import ConverseRescueClient, RescueExtractionRequest
from app.recovery.interpreter import RescueExtraction, RescueWordingRequest
from app.recovery.models import RecoveryOption
from app.schemas.request import TripRequest


def _request(message, history=None):
    return RescueExtractionRequest(trip=TripRequest(origin="Chennai", destination="Hyderabad",
        start_date=date(2026, 12, 1), end_date=date(2026, 12, 3)),
        itinerary={"return_transport": {"mode": "bus", "leg": "Hyderabad to Chennai"}},
        history=history or [], message=message)


def test_converse_extracts_missed_return_bus_with_history_and_traffic(monkeypatch):
    async def run():
        monkeypatch.setattr(settings, "bedrock_api_key", "test-key")
        monkeypatch.setattr(settings, "bedrock_converse_model_id", "test-model")
        monkeypatch.setattr(settings, "bedrock_region", "test-region")
        responses = [
            {"disruption_type": "missed", "affected_item": "return_bus", "cause": None,
             "already_arrived": False, "missing_info": ["current_location"],
             "next_question": "Where are you now?", "ready_to_replan": False},
            {"disruption_type": "missed", "affected_item": "return_bus", "cause": "traffic",
             "already_arrived": False, "missing_info": [], "next_question": None,
             "ready_to_replan": True},
            {"disruption_type": "cancelled", "affected_item": "train", "cause": None,
             "already_arrived": None, "missing_info": [], "next_question": None,
             "ready_to_replan": True},
        ]
        seen = []
        def handler(request):
            body = json.loads(request.content)
            seen.append(body)
            assert body["inferenceConfig"]["temperature"] == 0.1
            assert "Hyderabad to Chennai" in body["messages"][0]["content"][0]["text"]
            return httpx.Response(200, json={"output": {"message": {"content": [
                {"text": "```json\n" + json.dumps(responses.pop(0)) + "\n```"}]}}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            interpreter = ConverseRescueClient(client)
            first = await interpreter.extract(_request("i left the return bus"))
            assert (first.disruption_type, first.affected_item, first.ready_to_replan) == (
                "missed", "return_bus", False)
            assert first.next_question == "Where are you now?"
            history = [{"role": "user", "text": "i left the return bus"},
                       {"role": "assistant", "text": first.next_question}]
            second = await interpreter.extract(_request("i left my return bus due to traffic", history))
            assert (second.disruption_type, second.affected_item, second.cause,
                    second.ready_to_replan) == ("missed", "return_bus", "traffic", True)
            assert "i left the return bus" in seen[1]["messages"][0]["content"][0]["text"]
            train = await interpreter.extract(_request("train is cancelled"))
            assert (train.disruption_type, train.affected_item) == ("cancelled", "train")
    asyncio.run(run())


def test_converse_retries_malformed_json_once(monkeypatch):
    async def run():
        monkeypatch.setattr(settings, "bedrock_api_key", "test-key")
        monkeypatch.setattr(settings, "bedrock_converse_model_id", "test-model")
        monkeypatch.setattr(settings, "bedrock_region", "test-region")
        attempts = 0
        def handler(_request):
            nonlocal attempts
            attempts += 1
            text = "not JSON" if attempts == 1 else json.dumps({
                "disruption_type": "cancelled", "affected_item": "train", "cause": None,
                "already_arrived": None, "missing_info": [], "next_question": None,
                "ready_to_replan": True})
            return httpx.Response(200, json={"output": {"message": {"content": [{"text": text}]}}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await ConverseRescueClient(client).extract(_request("train is cancelled"))
        assert attempts == 2
        assert result.affected_item == "train"
    asyncio.run(run())


def test_wording_rejects_reordered_options_that_would_mismatch_buttons(monkeypatch):
    async def run():
        monkeypatch.setattr(settings, "bedrock_api_key", "test-key")
        monkeypatch.setattr(settings, "bedrock_converse_model_id", "test-model")
        monkeypatch.setattr(settings, "bedrock_region", "test-region")
        def handler(_request):
            return httpx.Response(200, json={"output": {"message": {"content": [{
                "text": json.dumps({"reply": "1. Evening train ₹800. 2. Next bus ₹1,000. Which option?"})
            }]}}})
        extraction = RescueExtraction(disruption_type="missed", affected_item="return_bus",
            cause="traffic", already_arrived=False, missing_info=[], next_question=None,
            ready_to_replan=True)
        options = [RecoveryOption(id="return:bus:1", category="mobility", title="Next bus",
                                  reason="Bus result", price=1000),
                   RecoveryOption(id="return:train:2", category="mobility", title="Evening train",
                                  reason="Train result", price=800)]
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            try:
                await ConverseRescueClient(client).word_options(RescueWordingRequest(
                    trip=_request("train is cancelled").trip, extracted_fields=extraction,
                    options=options))
                assert False, "Reordered model wording must not be sent with the original buttons"
            except ValueError as exc:
                assert "reordered" in str(exc)
    asyncio.run(run())
