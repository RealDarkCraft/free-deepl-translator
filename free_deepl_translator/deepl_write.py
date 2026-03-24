from __future__ import annotations
import asyncio
import uuid
from typing import Any, Dict, List, Optional, Union

import msgpack

from .deepl_connector import DeeplConnection
from .deepl_loop import DeeplLoop
from .deepl_msgpack import msgpackPack
from .deepl_property import PropertyFunction
from .deepl_protobuf import proto_encode


class DeeplWrite:
    """Client DeepL Write (réécriture / reformulation) basé sur SignalR/WebSocket."""

    def __init__(self):
        self.property = PropertyFunction("write", self)
        self.loop = DeeplLoop(self)
        self.connection: Optional[DeeplConnection] = None
        self.term: List[Dict] = []
        self.style: Dict[str, Optional[str]] = {"current": None, "choosed": None}
        self.session: Dict[str, Any] = {"sessionMode": 2, "translatorSessionOptions": {}}

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def Session(
        self,
        version: int = 1,
        auth: str = "free",
        mode: str = "websocket",
        experimental: bool = False,
    ) -> bool:
        return self.loop.run(self.SessionAsync(version, auth, mode, experimental), False)

    async def SessionAsync(
        self,
        version: int = 1,
        auth: str = "free",
        mode: str = "websocket",
        experimental: bool = False,
    ) -> bool:
        if self.connection is not None:
            await self.loop.aRun(self.CloseAsync())
        if auth not in ("free", "pro") or mode not in ("websocket", "longpolling"):
            return False
        self.connection = DeeplConnection(self, version, auth, mode, experimental)
        self.property.connection = self.connection
        await self.loop.aRun(self.connection.deepl_connect(self.session))
        await self.loop.aRun(self.WriteOptionAsync("language", "en-US"))
        return bool(self.connection.status)

    def Close(self) -> None:
        if self.connection:
            self.loop.run(self.CloseAsync())

    async def CloseAsync(self) -> None:
        if self.connection:
            await self.loop.aRun(self.connection.close())
        self.connection = None
        self.property.connection = None
        self.loop.destroy()

    # ------------------------------------------------------------------
    # Options
    # ------------------------------------------------------------------

    def GetWriteOptions(self, _property: str) -> Optional[List]:
        return self.loop.run(self.GetWriteOptionsAsync(_property), None)

    async def GetWriteOptionsAsync(self, _property: str) -> Optional[List]:
        mapping = {"languages": "writeLanguagesValue", "styles": "writeStyleVariantsValue"}
        key = mapping.get(_property)
        if key and self.property.config.get(key) is not None:
            return list(self.property.config[key])
        return None

    def WriteOption(self, _property: str, value: Any) -> bool:
        if self.loop is None:
            return False
        return self.loop.run(self.WriteOptionAsync(_property, value), False)

    async def WriteOptionAsync(self, _property: str, value: Any) -> bool:
        lst: List[Dict] = []

        if _property == "language" and isinstance(value, str):
            if value not in self.property.config.get("writeLanguagesValue", set()):
                return False
            if value not in self.property.config.get("writeGlossaryLanguagesValue", set()):
                lst.append(self._field_event(6, "propertyName", 26, "writeGlossaryListValue", {}))
            lst.append(self._field_event(6, "propertyName", 21, "writeRequestedLanguageValue",
                                         {"language": {"code": value}}))

        elif _property == "term" and isinstance(value, list) and (
            len(value) == 0 or value[0].get("term") is not None
        ):
            # DeepL currently does not support both “term” and “style” at the same time
            lst.append(self._field_event(6, "propertyName", 24, "writeStyleVariantValue", {}))
            self.term = value
            lst.append(self._field_event(6, "propertyName", 26, "writeGlossaryListValue",
                                         {"glossaryEntries": self.term}))

        elif _property == "reformulate" and isinstance(value, (bool, int)) and value in (0, 1, True, False):
            lst.append(self._field_event(6, "propertyName", 43, "writeCorrectionsOnlyValue",
                                         {"correctionsOnly": int(value)}))

        elif _property == "style" and isinstance(value, str):
            if value not in self.property.config.get("writeStyleVariantsValue", set()):
                return False
            lst.append(self._field_event(6, "propertyName", 26, "writeGlossaryListValue", {}))
            lst.append(self._field_event(6, "propertyName", 24, "writeStyleVariantValue",
                                         {"styleVariant": {"value": value}}))
        else:
            return False

        data = self._build_append_message(lst)
        self.connection.waiters["participant"] = asyncio.Event()
        await self.loop.aRun(self.connection.send(data))
        await self.loop.aRun(self.connection.waiters["participant"].wait())
        return not self.property.OnError

    # ------------------------------------------------------------------
    # Write / Rephrase
    # ------------------------------------------------------------------

    def Write(self, text: Optional[str] = None) -> Dict[str, Any]:
        return self.loop.run(self.WriteAsync(text), {"status": 1, "msg": "loop not initialized"})

    async def WriteAsync(self, text: Optional[str] = None) -> Dict[str, Any]:
        if text is not None:
            err = self._check_text_integrity(text)
            if err is not None:
                return err
            max_len = self.property.config.get("writeMaximumTextLengthValue")
            if max_len is None or len(text) >= max_len:
                return {"status": 1, "msg": f"Text must not exceed {max_len} characters"}

            events = [{
                "fieldName": 5,
                "textChangeOperation": {
                    "range": {"end": len(self.property.fields[self.property.fieldName]["source"]["text"])},
                    "text": text,
                },
                "participantId": {"value": 2},
            }]
            self.property.fields[self.property.fieldName]["source"]["text"] = text
            data = self._build_append_message(events, raw=True)
            self.connection.waiters["participant"] = asyncio.Event()
            await self.loop.aRun(self.connection.send(data))
            await self.loop.aRun(self.connection.waiters["participant"].wait())
            if self.property.OnError:
                return {"status": 1, "msg": self.property.OnErrorLast}

        alternatives: set = set()
        for value in self.property.annotations.values():
            payload = value.get("writeProvidedAutomaticTextUnitAlternativesPayload")
            if payload is None:
                continue
            alts = payload.get("alternatives")
            if not alts or payload.get("flowId") is not None:
                continue
            if isinstance(alts, dict):
                alts = [alts]
            for alt in alts:
                if alt.get("text"):
                    alternatives.add(alt["text"])

        return {
            "status": 0,
            "text": self.property.fields[self.property.fieldName]["target"]["text"],
            "alternatives": list(alternatives),
        }

    def Rephrase(self, text: Optional[str] = None, line_index: int = 1) -> Dict[str, Any]:
        return self.loop.run(
            self.RephraseAsync(text, line_index),
            {"status": 1, "msg": "loop not initialized"},
        )

    async def RephraseAsync(
        self, text: Optional[str] = None, line_index: int = 1
    ) -> Dict[str, Any]:
        if text is not None:
            r = await self.loop.aRun(self.WriteAsync(text))
            if r["status"] != 0:
                return r

        target_text = self.property.fields[self.property.fieldName]["target"]["text"]
        lines = target_text.split("\n")
        non_empty_lines = [l for l in lines if l.strip()]
        if not non_empty_lines:
            return {"status": 1, "msg": "Empty text"}

        # Clamp line_index
        if line_index < 1 or line_index > len(non_empty_lines):
            line_index = 1

        # Compute char offset for the requested line
        range_val = 0
        line_counter = 1
        for line in lines:
            range_val += len(line)
            if line_counter == line_index:
                break
            if line.strip():
                line_counter += 1
            range_val += 1  # newline character

        annotation_uuid = str(uuid.uuid4())
        flow_id = str(uuid.uuid4())
        annotation = {
            "annotationId": {"value": annotation_uuid},
            "range": {"start": range_val, "end": range_val},
            "requestTextUnitAlternativesPayload": {"flowId": {"value": flow_id}},
        }
        events = [{
            "fieldName": 6,
            "createAnnotationOperation": annotation,
            "participantId": {"value": 2},
        }]
        data = self._build_append_message(events, raw=True)
        self.connection.waiters["participant"] = asyncio.Event()
        await self.loop.aRun(self.connection.send(data))
        await self.loop.aRun(self.connection.waiters["participant"].wait())

        textes: set = set()
        for value in self.property.annotations.values():
            payload = value.get("writeProvidedTextUnitAlternativesPayload")
            if payload is None:
                continue
            alts = payload.get("alternatives")
            flow = payload.get("flowId")
            if not alts or flow is None or flow.get("value") != flow_id:
                continue
            if isinstance(alts, dict):
                alts = [alts]
            for alt in alts:
                if alt.get("text"):
                    textes.add(alt["text"])

        return {"status": 0, "alternatives": list(textes)}

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _check_text_integrity(self, text: str) -> Optional[Dict[str, Any]]:
        if self.connection is None or self.connection.status is None:
            return {"status": 1, "msg": 'Not connected to a session. Did you call Session()?'}
        if self.connection.status is False:
            return {"status": 1, "msg": "Invalid session (may have broken due to an error)"}
        max_len = self.property.config.get("writeMaximumTextLengthValue", 0)
        if len(text) >= max_len:
            return {"status": 1, "msg": f"Text must not exceed {max_len} characters"}
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _field_event(field_name: int, prop_key: str, prop_name: int, value_key: str, value: Any) -> Dict:
        return {
            "fieldName": field_name,
            "setPropertyOperation": {prop_key: prop_name, value_key: value},
            "participantId": {"value": 2},
        }

    def _build_append_message(self, events: List, raw: bool = False) -> bytes:
        """Encodes a list of events into a msgpack message ready for sending."""
        data = {
            "appendMessage": {
                "events": events if raw else [e.toObj() for e in events],
                "baseVersion": {"version": {"value": self.property.base_version}},
            }
        }
        return msgpackPack([
            [
                2, {}, self.connection.config.get("send"),
                msgpack.ExtType(4, bytes(proto_encode(data, "ParticipantRequest"))),
            ]
        ])
