"""
Pydantic models for Meta WhatsApp Cloud API incoming webhook payloads.
Provides clean normalization into an internal IncomingMessage structure.
"""

from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class MessageType(str, Enum):
    TEXT = "text"
    INTERACTIVE = "interactive"
    BUTTON = "button"
    LOCATION = "location"
    IMAGE = "image"
    AUDIO = "audio"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


class ButtonReply(BaseModel):
    id: str
    title: str


class ListReply(BaseModel):
    id: str
    title: str
    description: Optional[str] = None


class InteractivePayload(BaseModel):
    type: str  # button_reply or list_reply
    button_reply: Optional[ButtonReply] = None
    list_reply: Optional[ListReply] = None


class TextPayload(BaseModel):
    body: str


class ContactProfile(BaseModel):
    name: Optional[str] = None


class Contact(BaseModel):
    profile: Optional[ContactProfile] = None
    wa_id: str


class RawMessage(BaseModel):
    id: str
    from_: str = Field(..., alias="from")
    timestamp: str
    type: str
    text: Optional[TextPayload] = None
    interactive: Optional[InteractivePayload] = None


class Value(BaseModel):
    messaging_product: Optional[str] = None
    contacts: Optional[List[Contact]] = None
    messages: Optional[List[RawMessage]] = None
    statuses: Optional[List[Dict[str, Any]]] = None


class Change(BaseModel):
    value: Value
    field: str


class Entry(BaseModel):
    id: str
    changes: List[Change]


class WebhookPayload(BaseModel):
    object: str
    entry: List[Entry]


class NormalizedEvent(BaseModel):
    """Normalized application-level event extracted from raw webhook payload."""
    wa_id: str
    user_name: str = "Traveler"
    message_id: str
    timestamp: str
    message_type: MessageType
    text: str = ""
    payload_id: Optional[str] = None  # Button ID or List ID if interactive

    @classmethod
    def from_raw_message(cls, msg: RawMessage, contact: Optional[Contact] = None) -> "NormalizedEvent":
        user_name = (contact.profile.name if contact and contact.profile else "Traveler") or "Traveler"
        wa_id = msg.from_

        if msg.type == "text" and msg.text:
            return cls(
                wa_id=wa_id,
                user_name=user_name,
                message_id=msg.id,
                timestamp=msg.timestamp,
                message_type=MessageType.TEXT,
                text=msg.text.body.strip(),
            )
        elif msg.type == "interactive" and msg.interactive:
            if msg.interactive.button_reply:
                return cls(
                    wa_id=wa_id,
                    user_name=user_name,
                    message_id=msg.id,
                    timestamp=msg.timestamp,
                    message_type=MessageType.INTERACTIVE,
                    text=msg.interactive.button_reply.title.strip(),
                    payload_id=msg.interactive.button_reply.id,
                )
            elif msg.interactive.list_reply:
                return cls(
                    wa_id=wa_id,
                    user_name=user_name,
                    message_id=msg.id,
                    timestamp=msg.timestamp,
                    message_type=MessageType.INTERACTIVE,
                    text=msg.interactive.list_reply.title.strip(),
                    payload_id=msg.interactive.list_reply.id,
                )
        elif msg.type == "button":
            # Quick reply button legacy format
            return cls(
                wa_id=wa_id,
                user_name=user_name,
                message_id=msg.id,
                timestamp=msg.timestamp,
                message_type=MessageType.BUTTON,
                text=msg.text.body if msg.text else "",
            )

        return cls(
            wa_id=wa_id,
            user_name=user_name,
            message_id=msg.id,
            timestamp=msg.timestamp,
            message_type=MessageType.UNKNOWN,
            text="",
        )
