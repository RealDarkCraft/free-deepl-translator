from __future__ import annotations
import asyncio
import json
import os
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Dict, List, Optional

import msgpack

from .deepl_protobuf import proto_decode, proto_encode
from .deepl_msgpack import msgpackPack, msgpackUnpack

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_EXT_TYPE_DEF: Dict[str, Optional[str]] = json.loads(
    open(os.path.join(MODULE_DIR, "json", "protobuf_exttype.json"), encoding="utf-8").read()
)


class MessageType(IntEnum):
    """SignalR message types."""
    INVOCATION = 1
    STREAM_ITEM = 2
    COMPLETION = 3
    STREAM_INVOCATION = 4
    CANCEL_INVOCATION = 5
    PING = 6
    CLOSE = 7


class CompletionResult(IntEnum):
    """Types of results for completion messages."""
    ERROR = 1
    VOID = 2
    NON_VOID = 3


@dataclass
class SignalRMessage:
    """Represents a decoded SignalR message."""
    type: MessageType
    headers: dict
    invocation_id: Optional[str] = None
    target: Optional[str] = None
    arguments: Optional[List[Any]] = None
    streams_ids: Optional[List[Any]] = None
    result_type: Optional[Any] = None
    result: Optional[Any] = None
    error: Optional[Any] = None

    @classmethod
    def from_msgpack(cls, data: list) -> "SignalRMessage":
        """Creates a SignalRMessage from decoded msgpack data."""
        msg_type = MessageType(data[0])
        headers = data[1] if len(data) > 1 else {}
        msg = cls(type=msg_type, headers=headers)

        if msg_type == MessageType.INVOCATION:
            msg.invocation_id = data[2] if len(data) > 2 else None
            msg.target = data[3] if len(data) > 3 else None
            msg.arguments = data[4] if len(data) > 4 else []
            msg.streams_ids = data[5] if len(data) > 5 else []

        elif msg_type == MessageType.STREAM_ITEM:
            msg.invocation_id = data[2] if len(data) > 2 else None
            msg.result = data[3] if len(data) > 3 else None

        elif msg_type == MessageType.COMPLETION:
            msg.invocation_id = data[2] if len(data) > 2 else None
            msg.result_type = data[3] if len(data) > 3 else None
            if msg.result_type == CompletionResult.ERROR:
                msg.error = data[4] if len(data) > 4 else None
            elif msg.result_type == CompletionResult.NON_VOID:
                msg.result = data[4] if len(data) > 4 else None

        return msg

    def is_invocation(self) -> bool:
        return self.type == MessageType.INVOCATION

    def is_stream_item(self) -> bool:
        return self.type == MessageType.STREAM_ITEM

    def is_completion(self) -> bool:
        return self.type == MessageType.COMPLETION

    def is_ping(self) -> bool:
        return self.type == MessageType.PING


class SignalRFunctionsMapping:
    """Maps Protobuf message types to processing functions."""

    def __init__(self, parent: "SignalRMessageHandler"):
        self.parent = parent
        self.property = parent.property
        self.map: Dict[str, Any] = self._build_map([
            ("StartSessionRequest", None),
            ("StartSessionResponse", self.property.Function_StartSessionResponse),
            ("ParticipantRequest", None),
            ("ParticipantResponse", self.property.Function_ParticipantResponse),
            ("signalr.ClientErrorInfo", self.property.Function_OnError),
        ])
        self.invoke_map: Dict[str, Any] = {
            "OnError": self.property.Function_OnError,
            "AppendResponse": self.property.Function_AppendResponse,
        }

    def _build_map(self, mapping: List[tuple]) -> Dict[str, Any]:
        lookup = {name: func for name, func in mapping}
        result: Dict[str, Any] = {}
        for ext_key, proto_name in _EXT_TYPE_DEF.items():
            if proto_name is None:
                continue
            func = lookup.get(proto_name)
            if func is not None:
                result[ext_key] = func
        return result


class SignalRMessageHandler:
    """Handles the receipt and dispatch of SignalR messages."""

    def __init__(self, connector: Any):
        self.client = connector
        self.property = self.client.property
        self.signalrMapping = SignalRFunctionsMapping(self)

    async def format_res(self, res: bytes) -> None:
        """The main entry point for processing an incoming message."""
        if self.client._is_closing:
            return

        if not self.client.is_handshaked:
            await self._handle_handshake(res)
            return

        for msg in self._parse_messages(res):
            await self._handle_message(msg)

    async def _handle_handshake(self, res: bytes) -> None:
        handshake_data = json.loads(res[:-1].decode())
        task = asyncio.create_task(self.client.Handshake(handshake_data))
        self.client.collector.append(task)

    def _parse_messages(self, res: bytes) -> List[SignalRMessage]:
        raw = msgpackUnpack(res)
        return [SignalRMessage.from_msgpack(msg) for msg in raw]

    async def _handle_message(self, msg: SignalRMessage) -> None:
        if msg.is_invocation():
            await self._handle_invocation(msg)
        elif msg.is_stream_item():
            await self._handle_stream_item(msg)
        elif msg.is_completion():
            await self._handle_completion(msg)
        elif msg.is_ping():
            await self._handle_ping()

    async def _handle_invocation(self, msg: SignalRMessage) -> None:
        decoded_args = [
            (proto_decode(arg.data, arg.code)[0], str(arg.code))
            for arg in msg.arguments
        ]
        func = self.signalrMapping.invoke_map.get(str(msg.target))
        if func is not None:
            func(decoded_args)
        else:
            self.client.logger.Error(f"Unknown invocation target: {msg.target}")
            await self._handle_close()
            return

        await self.client.send(msgpackPack([
            [5, {}, self.client.config.get("recv")]
        ]))

    async def _handle_stream_item(self, msg: SignalRMessage) -> None:
        element = msg.result
        if element and hasattr(element, "code"):
            decoded = proto_decode(element.data, element.code)[0]
            func = self.signalrMapping.map.get(str(element.code))
            if func is not None:
                func(decoded)
            else:
                self.client.logger.Error(f"Unknown stream item code: {element.code}")
                await self._handle_close()

    async def _handle_completion(self, msg: SignalRMessage) -> None:
        if msg.result_type == CompletionResult.NON_VOID:
            protobuf_res = msg.result
            if protobuf_res and hasattr(protobuf_res, "code"):
                decoded = proto_decode(protobuf_res.data, protobuf_res.code)[0]
                func = self.signalrMapping.map.get(str(protobuf_res.code))
                if func is not None:
                    task = asyncio.create_task(func(decoded))
                    self.client.collector.append(task)
                else:
                    self.client.logger.Error(f"Unknown completion code: {protobuf_res.code}")
                    await self._handle_close()
        elif msg.result_type == CompletionResult.VOID:
            await self._handle_close()

    async def _handle_close(self) -> None:
        self.client._is_closing = True
        await self.client.close()
        self.client.status = False
        self.client._set_all_waiters()

    async def _handle_ping(self) -> None:
        self.client.logger.Info("Ping received")
        with open("j.txt", "a") as f:
            f.write("b")
        pong = [MessageType.PING]
        task = asyncio.create_task(self.client.send(msgpackPack([pong])))
        self.client.collector.append(task)
        self.client.logger.Info("Ping sent")
