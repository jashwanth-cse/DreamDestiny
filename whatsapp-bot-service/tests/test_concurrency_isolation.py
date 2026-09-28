import pytest
import asyncio
from app.schemas.webhook import NormalizedEvent, MessageType
from app.conversation.manager import conversation_manager
from app.storage.redis_store import redis_store
from app.whatsapp.client import whatsapp_client
from app.schemas.conversation import ConversationState


@pytest.mark.asyncio
async def test_multi_user_isolation():
    """
    Simulate two users chatting concurrently and verify complete isolation of
    draft state and responses (Section 12 of specification).
    """
    whatsapp_client.clear_sent_messages()

    user_a = "919000000001"
    user_b = "919000000002"

    # User A wants to go to Goa
    event_a = NormalizedEvent(
        wa_id=user_a,
        user_name="Alice",
        message_id="msg_a_1",
        timestamp="1727440001",
        message_type=MessageType.TEXT,
        text="Plan a trip to Goa",
    )

    # User B wants to go to Manali
    event_b = NormalizedEvent(
        wa_id=user_b,
        user_name="Bob",
        message_id="msg_b_1",
        timestamp="1727440002",
        message_type=MessageType.TEXT,
        text="Plan a trip to Manali",
    )

    # Process concurrently
    await asyncio.gather(
        conversation_manager.process_incoming_event(event_a),
        conversation_manager.process_incoming_event(event_b),
    )

    session_a = await redis_store.get_session(user_a)
    session_b = await redis_store.get_session(user_b)

    assert session_a is not None
    assert session_b is not None

    # Check isolation: User A draft has Goa, User B draft has Manali
    assert session_a.draft.destination == "Goa"
    assert session_b.draft.destination == "Manali"

    # Verify outgoing messages were addressed to the correct recipient
    sent = whatsapp_client.get_sent_messages()
    assert len(sent) == 2

    to_recipients = {s["to"] for s in sent}
    assert user_a in to_recipients
    assert user_b in to_recipients


@pytest.mark.asyncio
async def test_webhook_idempotency_deduplication():
    """
    Verify that duplicate webhook deliveries for the same message_id are processed only once
    (Section 14 of specification).
    """
    whatsapp_client.clear_sent_messages()

    event = NormalizedEvent(
        wa_id="919999999999",
        user_name="Charlie",
        message_id="dup_msg_123",
        timestamp="1727440000",
        message_type=MessageType.TEXT,
        text="Hello",
    )

    # First delivery
    await conversation_manager.process_incoming_event(event)
    sent_count_1 = len(whatsapp_client.get_sent_messages())
    assert sent_count_1 == 1

    # Second delivery (duplicate delivery by Meta webhook)
    await conversation_manager.process_incoming_event(event)
    sent_count_2 = len(whatsapp_client.get_sent_messages())

    # Count must remain 1 — duplicate was safely dropped!
    assert sent_count_2 == 1
