from __future__ import annotations
from typing import Any, Dict, List, Optional

import msgpack

from .deepl_msgpack import msgpackPack
from .deepl_translator_type import getSendProperty


class PropertyFunction:
    """Manages the shared state of a DeepL session (fields, configuration, annotations)."""

    def __init__(self, fieldName: str, parent: Any):
        self.connection: Optional[Any] = None
        self.parent = parent
        self.fieldName = fieldName
        self.fields: Dict[str, Any] = {
            "translator": {
                "source": {"text": ""},
                "target": {"text": ""},
                "target_transcription": {},
            },
            "write": {
                "source": {"text": ""},
                "target": {"text": ""},
            },
        }
        self.annotations: Dict[str, Any] = {}
        self.metaInfoMessage: Dict[str, Any] = {"translatorTaskMetaInfo": 0}
        self.config: Dict[str, Any] = {}
        self.property: Dict[str, Any] = {"send": getSendProperty()}
        self.OnError: bool = False
        self.OnErrorLast: str = ""
        self.base_version: int = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def PropertySend(self, propertyName: str) -> Optional[type]:
        sender = self.property.get("send")
        if sender is not None:
            return sender.get(propertyName)
        return None

    @staticmethod
    def TextChangeOperation(
        original_text: str, new_text: str, range_: Optional[Dict]
    ) -> str:
        """Applies a text replacement operation to a range."""
        if not isinstance(original_text, str) or not isinstance(new_text, str):
            return original_text
        start = 0
        end = 0
        if isinstance(range_, dict):
            start = range_.get("start", 0) if isinstance(range_.get("start"), int) else 0
            end = range_.get("end", 0) if isinstance(range_.get("end"), int) else 0
        return f"{original_text[:start]}{new_text}{original_text[end:]}"

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def Function_OnError(self, errors: List[Any] = []) -> None:
        for error in errors:
            self.OnErrorLast = error[0]["detailCode"]["value"]
            self.OnError = True

    def Function_AppendResponse(self, resps: List[Any] = []) -> None:
        for resp in resps:
            func = self.connection.signalR.signalrMapping.map.get(resp[1])
            if func is not None:
                func(resp[0])
            else:
                self.connection.logger.Error(f"Unk func : {resp[1]}")

    def Function_SetPropertyOperation(self, event: Dict[str, Any]) -> None:
        prop = event.get("propertyName")

        def _add_langs(key: str, langs_key: str, lang_list: List[Dict]) -> None:
            if self.config.get(key) is None:
                self.config[key] = set()
            for lang in lang_list:
                code = lang["code"]
                if "-" in code:
                    self.config[key].add(code.split("-")[0])
                self.config[key].add(code)

        if prop == 1:
            _add_langs(
                "translatorSourceLanguagesValue",
                "sourceLanguages",
                event["translatorSourceLanguagesValue"]["sourceLanguages"],
            )
        elif prop == 2:
            _add_langs(
                "translatorTargetLanguagesValue",
                "targetLanguages",
                event["translatorTargetLanguagesValue"]["targetLanguages"],
            )
            # Alias courts toujours acceptés
            self.config["translatorTargetLanguagesValue"].update({"es", "en"})
        elif prop == 14:
            self.config["translatorMaximumTextLengthValue"] = event[
                "translatorMaximumTextLengthValue"
            ]["max"]
        elif prop == 16:
            self.config["translatorLanguageModelValue"] = event[
                "translatorLanguageModelValue"
            ]["languageModel"]["value"]
        elif prop == 20:
            _add_langs(
                "writeLanguagesValue",
                "languages",
                event["writeLanguagesValue"]["languages"],
            )
        elif prop == 23:
            if self.config.get("writeStyleVariantsValue") is None:
                self.config["writeStyleVariantsValue"] = set()
            for variant in event["writeStyleVariantsValue"]["styleVariants"]:
                self.config["writeStyleVariantsValue"].add(variant["value"])
        elif prop == 28:
            self.config["writeMaximumTextLengthValue"] = event[
                "writeMaximumTextLengthValue"
            ]["max"]
        elif prop == 31:
            _add_langs(
                "writeGlossaryLanguagesValue",
                "languages",
                event["writeGlossaryLanguagesValue"]["languages"],
            )

    def Function_FieldEvent(self, event: Dict[str, Any]) -> None:
        field = self.fieldName

        text_op = event.get("textChangeOperation")
        if text_op is not None:
            field_name = event["fieldName"]
            # Source fields: 1, 5; target fields: 2, 6
            if field_name in (1, 5):
                self.fields[field]["source"]["text"] = self.TextChangeOperation(
                    self.fields[field]["source"]["text"],
                    text_op.get("text"),
                    text_op.get("range"),
                )
            elif field_name in (2, 6):
                self.fields[field]["target"]["text"] = self.TextChangeOperation(
                    self.fields[field]["target"]["text"],
                    text_op.get("text"),
                    text_op.get("range"),
                )

        if event.get("setPropertyOperation") is not None:
            self.Function_SetPropertyOperation(event["setPropertyOperation"])

        create_op = event.get("createAnnotationOperation")
        if create_op is not None:
            annotation_id = create_op["annotationId"]["value"]
            annotation_data = {k: v for k, v in create_op.items() if k != "annotationId"}
            self.annotations[annotation_id] = annotation_data

        remove_op = event.get("removeAnnotationOperation")
        if remove_op is not None:
            self.annotations.pop(
                remove_op["annotationId"]["value"], None
            )

    async def Function_StartSessionResponse(self, decoded: Dict[str, Any]) -> None:
        self.connection.SignalrSession.refresh(decoded)
        participate_msg = msgpackPack(
            [
                [
                    1,
                    {},
                    self.connection.config.get("recv"),
                    "Participate",
                    [msgpack.ExtType(code=3, data=b"")],
                ]
            ]
        )
        await self.connection.send(participate_msg)

    def Function_ParticipantResponse(self, resp: Dict[str, Any]) -> None:
        def _confirmed(parent: PropertyFunction, msg: Dict) -> None:
            pass  # Acknowledged, nothing to do

        def _published(parent: PropertyFunction, msg: Dict) -> None:
            if msg.get("currentVersion") is not None:
                parent.base_version = msg["currentVersion"]["version"]["value"]
            events = msg.get("events")
            if events is None:
                events = []
            elif isinstance(events, dict):
                events = [events]
            for evt in events:
                parent.Function_FieldEvent(evt)

        def _meta_info(parent: PropertyFunction, msg: Dict) -> None:
            idle = msg.get("idle")
            if idle is not None:
                if idle.get("eventVersion") is not None:
                    parent.base_version = idle["eventVersion"]["version"]["value"]
                if parent.connection.waiters.get("participant") is not None:
                    parent.connection.waiters["participant"].set()

        def _initialized(parent: PropertyFunction, msg: Dict) -> None:
            parent.connection.status = True
            parent.connection.waiters["handshake"].set()

        handlers = {
            "confirmedMessage": _confirmed,
            "publishedMessage": _published,
            "metaInfoMessage": _meta_info,
            "initializedMessage": _initialized,
        }
        for key, value in resp.items():
            handler = handlers.get(key)
            if handler:
                handler(self, value)
