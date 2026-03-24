from __future__ import annotations
import asyncio
from typing import Any, Dict, List, Optional

import msgpack

from .deepl_connector import DeeplConnection
from .deepl_loop import DeeplLoop
from .deepl_msgpack import msgpackPack
from .deepl_property import PropertyFunction
from .deepl_protobuf import proto_encode


_DEFAULT_SESSION = {
    "sessionMode": 1,
    "baseDocument": {
        "fields": [
            {
                "fieldName": 1,
                "properties": [
                    {
                        "propertyName": 14,
                        "translatorMaximumTextLengthValue": {"max": 1500},
                    }
                ],
            },
            {
                "fieldName": 2,
                "properties": [
                    {
                        "propertyName": 5,
                        "translatorRequestedTargetLanguageValue": {
                            "targetLanguage": {"code": "en-US"}
                        },
                    },
                    {
                        "propertyName": 18,
                        "translatorCalculatedTargetLanguageValue": {
                            "targetLanguage": {"code": "en-US"}
                        },
                    },
                ],
            },
        ]
    },
    "translatorSessionOptions": {"enableTranslatorQuoteConversion": 1},
}


class DeeplTranslator:
    """DeepL translation client based on the SignalR/WebSocket protocol."""

    def __init__(self):
        self.property = PropertyFunction("translator", self)
        self.connection: Optional[DeeplConnection] = None
        self.loop = DeeplLoop(self)
        self.session = _DEFAULT_SESSION

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def Session(
        self,
        auth: str = "free",
        mode: str = "websocket",
        experimental: bool = False,
    ) -> bool:
        return self.loop.run(self.SessionAsync(auth, mode, experimental), False)

    async def SessionAsync(
        self,
        auth: str = "free",
        mode: str = "websocket",
        experimental: bool = False,
    ) -> bool:
        if self.connection is not None:
            await self.loop.aRun(self.CloseAsync())
        if auth not in ("free", "pro") or mode not in ("websocket", "longpolling"):
            return False
        self.connection = DeeplConnection(self, auth, mode, experimental)
        self.property.connection = self.connection
        await self.loop.aRun(self.connection.deepl_connect(self.session))
        return bool(self.connection.status)

    def Close(self) -> None:
        if self.connection:
            self.loop.run(self.CloseAsync())
        self.loop.tryJoin()

    async def CloseAsync(self) -> None:
        if self.connection:
            await self.loop.aRun(self.connection.close())
        self.connection = None
        self.property.connection = None
        self.loop.destroy()
        self.loop.tryJoin()

    # ------------------------------------------------------------------
    # Translation
    # ------------------------------------------------------------------

    def Translate(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str] = None,
        target_model: Optional[str] = None,
        glossary: Optional[List[Dict]] = None,
        formality: Optional[Any] = None,
    ) -> Dict[str, Any]:
        return self.loop.run(
            self.TranslateAsync(text, target_lang, source_lang, target_model, glossary, formality),
            {"status": 1, "msg": "loop not initialized"},
        )

    async def TranslateAsync(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str] = None,
        target_model: Optional[str] = None,
        glossary: Optional[List[Dict]] = None,
        formality: Optional[Any] = None,
    ) -> Dict[str, Any]:
        err = self._check_text_integrity(text, target_lang, source_lang)
        if err is not None:
            return err
        result = await self.loop.aRun(
            self._get_translations(text, target_lang, source_lang, target_model, glossary, formality)
        )
        if result == "":
            return {"status": 1, "msg": ""}
        if result is None:
            return {"status": 1, "msg": self.property.OnErrorLast}
        return {"status": 0, **result}

    async def _get_translations(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str],
        target_model: Optional[str],
        glossary: Optional[List[Dict]],
        formality: Optional[Any],
    ) -> Optional[Dict[str, Any]]:
        send = self.property.PropertySend
        lst = []

        # Formality
        if formality is not None:
            lst.append(send("FieldEvent")(2, 2, setPropertyOperation={
                "propertyName": 8,
                "translatorFormalityModeValue": {"formalityMode": {"value": formality}},
            }))
        else:
            lst.append(send("FieldEvent")(2, 2, setPropertyOperation={
                "propertyName": 8,
                "translatorFormalityModeValue": {"formalityMode": {}},
            }))

        # Glossary
        if isinstance(glossary, list):
            entries = [
                {"1": g["source"], "2": g["target"]}
                for g in glossary
                if isinstance(g, dict)
                and g.get("source") and g.get("target")
                and g["source"].strip() and g["target"].strip()
            ]
            glossary_value: Any = entries[0] if len(entries) == 1 else entries
            lst.append(send("FieldEvent")(2, 2, setPropertyOperation={
                "propertyName": 10,
                "translatorGlossaryListValue": {"glossaryEntries": glossary_value},
            }))
        else:
            lst.append(send("FieldEvent")(2, 2, setPropertyOperation={
                "propertyName": 10,
                "translatorGlossaryListValue": {"glossaryEntries": []},
            }))

        # Target language
        lst.append(send("FieldEvent")(2, 2, setPropertyOperation={
            "propertyName": 5,
            "translatorRequestedTargetLanguageValue": {"targetLanguage": {"code": target_lang}},
        }))

        # Source language
        if source_lang is None:
            lst.append(send("FieldEvent")(1, 2, setPropertyOperation={"propertyName": 3}))
        else:
            lst.append(send("FieldEvent")(1, 2, setPropertyOperation={
                "propertyName": 3,
                "translatorRequestedSourceLanguageValue": {"sourceLanguage": {"code": source_lang}},
            }))

        # Model
        if target_model is not None:
            lst.append(send("FieldEvent")(2, 2, setPropertyOperation={
                "propertyName": 16,
                "translatorLanguageModelValue": {"languageModel": {"value": target_model}},
            }))

        # Text change
        current_len = len(self.property.fields[self.property.fieldName]["source"]["text"])
        lst.append(send("FieldEvent")(1, 2, textChangeOperation={
            "range": {"end": current_len},
            "text": text,
        }))

        request_obj = send("ParticipantRequest")(
            send("AppendMessage")(lst, self.property.base_version)
        ).toObj()

        self.property.fields[self.property.fieldName]["source"]["text"] = text

        if self.connection.config.get("mode") == "stream":
            payload = msgpackPack([
                [
                    2, {}, self.connection.config["send"],
                    msgpack.ExtType(4, bytes(proto_encode(request_obj, "ParticipantRequest"))),
                ]
            ])
        else:  # invoke
            payload = msgpackPack([
                [
                    1, {}, self.connection.config["send"], "AppendRequest",
                    [msgpack.ExtType(4, bytes(proto_encode(request_obj, "ParticipantRequest")))],
                ]
            ])

        self.connection.waiters["participant"] = asyncio.Event()
        await self.connection.send(payload)
        self.property.metaInfoMessage["translatorTaskMetaInfo"] = 0
        await self.connection.waiters["participant"].wait()

        if self.property.OnError:
            return None

        alternatives: set = set()
        for value in self.property.annotations.values():
            alts_payload = value.get("translatorProvidedAutomaticTextUnitAlternativesPayload")
            if alts_payload is None:
                continue
            alts = alts_payload.get("alternatives")
            if not alts:
                continue
            if isinstance(alts, dict):
                alts = [alts]
            for alt in alts:
                if alt.get("text"):
                    alternatives.add(alt["text"])

        return {
            "text": self.property.fields[self.property.fieldName]["target"]["text"],
            "alternatives": list(alternatives),
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _check_text_integrity(
        self, text: str, target_lang: str, source_lang: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        if self.connection is None or self.connection.status is None:
            return {"status": 1, "msg": 'Not connected to a session. Did you call Session()?'}
        if self.connection.status is False:
            return {"status": 1, "msg": "Invalid session (may have broken due to an error)"}
        max_len = self.property.config.get("translatorMaximumTextLengthValue", 0)
        if len(text) >= max_len:
            return {"status": 1, "msg": f"Text must not exceed {max_len} characters"}
        if target_lang not in self.property.config.get("translatorTargetLanguagesValue", set()):
            return {"status": 1, "msg": f"Invalid target language: {target_lang}"}
        if source_lang is not None and source_lang not in self.property.config.get(
            "translatorSourceLanguagesValue", set()
        ):
            return {"status": 1, "msg": f"Invalid source language: {source_lang}"}
        return None

