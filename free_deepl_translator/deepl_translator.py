import json
import threading
import asyncio
import time
import base64
import curl_cffi
import msgpack
import blackboxprotobuf
from .deepl_protobuf import proto_decode, proto_encode
from .deepl_msgpack import msgpackPack, msgpackUnpack
from .deepl_connector import DeeplConnection
from .deepl_property import PropertyFunction

class DeeplTranslator:
    def __init__(self):
        self.property = PropertyFunction()
        self.loop = None
        self.connection = None
        self.input = ""
        self.output = ""
        self.last_status_code = 0
    def check_text_integrity(self, text, target_lang, source_lang):
        if self.connection == None or self.connection.status == None:
            return {"status":1,"msg":"Not connected to an session (Do you forget to call \"*.Session()\" ?)"}
        elif self.connection.status == False:
            return {"status":1,"msg":"Invalid Session (Session might break in case of errors)"}
        if (len(text) >= self.connection.config["maximum_text_length"]):
            return {"status":1,"msg":f"Text must not exceed <{self.max_text_len}> lenght"}
        if (target_lang not in self.connection.config["target_langs"]):
            return {"status":1,"msg":f"Invalid target language <{target_lang}>"}
        if (source_lang != None and source_lang not in self.connection.config["source_langs"]):
            return {"status":1,"msg":f"Invalid source language <{source_lang}>"}
        return None
    def Session(self, auth = "free", mode = "longpolling"):
        if (self.loop == None):
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        return self.loop.run_until_complete(self.SessionAsync(auth, mode))
    def Close(self):
        if (self.loop != None):
            self.loop.run_until_complete(self.CloseAsync())
            self.loop.close()
            self.loop = None
    async def CloseAsync(self):
        if (self.connection != None):
            await self.connection.close()
        self.connection = None
    async def SessionAsync(self, auth = "free", mode = "longpolling"):
        if (self.connection != None):
            await self.CloseAsync()
        if (auth not in ["free", "pro"] or mode not in ["websocket", "longpolling"]):
            return False
        self.connection = DeeplConnection(auth, mode)
        await self.connection.deepl_connect()
        return self.connection.status
    
    async def TranslateAsync(self, text, target_lang, source_lang = None, target_model = None, glossary = None, formality = None, is_async = True):
        if (self.loop != None and is_async == True):
            return False
        err = self.check_text_integrity(text, target_lang, source_lang)
        if (err != None):
            return err
        trans = await asyncio.create_task(self.get_translations(text, target_lang, source_lang, target_model, glossary, formality))
        if (trans ==  ""):
            return {"status":1,"msg":""}
        elif (trans == None):
            return {"status":1,"msg":self.connection.OnErrorLast}
        return {"status":0,"text":trans}

    def Translate(self, text, target_lang, source_lang = None, target_model = None, glossary = None, formality = None):
        if (self.loop == None):
            return {"status":1,"msg":""}
        return self.loop.run_until_complete(self.TranslateAsync(text, target_lang, source_lang, target_model, glossary, formality, False))
    async def get_translations(self, text, target_lang, source_lang = None, target_model = None, glossary = None, formality = None):
        lst = []
        if (formality != None):
            lst.append({"fieldName": 2, "setPropertyOperation": {"propertyName":8, "translatorFormalityModeValue":{"formalityMode":{"value":formality}}}, "participantId":{"value":2}})
        else:
            lst.append({"fieldName": 2, "setPropertyOperation": {"propertyName":8, "translatorFormalityModeValue":{"formalityMode":{}}}, "participantId":{"value":2}})
        if (type(glossary) == list):
            glosarry_lst = []
            for glossary_item in glossary:
                if (type(glossary_item) != dict or glossary_item.get("source") == None or glossary_item.get("target") == None or len(glossary_item.get("source").strip()) == 0 or len(glossary_item.get("target").strip()) == 0):
                    continue
                glosarry_lst.append({'1': glossary_item.get("source").encode(), '2': glossary_item.get("target").encode()})
            if (len(glosarry_lst) == 1):
                lst.append({'fieldName': 2, 'setPropertyOperation': {'propertyName': 10, 'translatorGlossaryListValue': {'glossaryEntries': glosarry_lst[0]}}, 'participantId': {'value': 2}})
            elif (len(glosarry_lst) > 1):
                lst.append({'fieldName': 2, 'setPropertyOperation': {'propertyName': 10, 'translatorGlossaryListValue': {'glossaryEntries': glosarry_lst}}, 'participantId': {'value': 2}})
        else:
            lst.append({'fieldName': 2, 'setPropertyOperation': {'propertyName': 10, 'translatorGlossaryListValue': {'glossaryEntries': []}}, 'participantId': {'value': 2}})
        lst.append({'fieldName': 2, 'setPropertyOperation': {'propertyName': 5, 'translatorRequestedTargetLanguageValue': {'targetLanguage': {'code': target_lang.encode()}}}, 'participantId': {'value': 2}})
        if (source_lang == None):
            lst.append({'fieldName': 1, 'setPropertyOperation': {'propertyName': 3}, 'participantId': {'value': 2}})
        else:
            lst.append({'fieldName': 1, 'setPropertyOperation': {'propertyName': 3, 'translatorRequestedSourceLanguageValue': {'sourceLanguage': {'code': source_lang.encode()}}}, 'participantId': {'value': 2}})
        if (target_model != None):
            lst.append({'fieldName': 2, 'setPropertyOperation': {'propertyName': 16, 'translatorLanguageModelValue': {'languageModel': {'value': target_model.encode()}}}, 'participantId': {'value': 2}})
        lst.append({'fieldName': 1, 'textChangeOperation': {'range': {"end":len(self.input)}, 'text': text.encode()}, 'participantId': {'value': 2}})
        translate_text = {'appendMessage': {'events': lst, 'baseVersion': {'version': {'value': self.connection.bver}}}}
        self.input = text
        translate = msgpackPack([msgpack.packb([2, {}, '1', msgpack.ExtType(4, bytes(proto_encode(translate_text, "ParticipantRequest")))])])    
        await self.connection.send(translate)
        msgs = await self.connection.pop_message()
        if (msgs == None or msgs[3] == "OnError"):
            return None
        msgs, data_type = proto_decode(msgs[3].data, "ParticipantResponse")
        if msgs == None or msgs.get("confirmedMessage") == None:
            return None
        true = True
        while true:
            i = await self.connection.pop_message()
            if (i == None or i[3] == "OnError"):
                return None
            js, data_type = proto_decode(i[3].data, "ParticipantResponse")
            if (js.get("metaInfoMessage") != None and js.get("metaInfoMessage").get("idle") != None):
                true = False
                break
            if (js.get("publishedMessage") != None):
                if (js["publishedMessage"].get("currentVersion") != None):
                    self.connection.bver = js["publishedMessage"]["currentVersion"]["version"]["value"]
                if js["publishedMessage"].get("events") != None:
                    events = js["publishedMessage"]["events"]
                    if (type(events) == dict):
                        events = [events]
                    for evt in events:
                        if (evt.get("textChangeOperation") != None):
                            var = evt.get("textChangeOperation")
                            if (evt["fieldName"] == 2):
                                self.output = self.property.TextChangeOperation(self.output, var.get("text"), var.get("range"))
                            elif (evt["fieldName"] == 1):
                                self.input = self.property.TextChangeOperation(self.input, var.get("text"), var.get("range"))
        return self.output