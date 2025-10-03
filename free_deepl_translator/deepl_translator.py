import json
import threading
import asyncio
import time
import base64
import curl_cffi
import msgpack
import blackboxprotobuf
from .deepl_protobuf import ProtobufRemoveNames, ProtobufAddNames
from .deepl_msgpack import msgpackPack, msgpackUnpack
from .deepl_connector import DeeplConnection

class DeeplTranslator:
    def __init__(self):
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
            return {"status":1,"msg":self.last_error}
        return {"status":0,"text":trans}

    def Translate(self, text, target_lang, source_lang = None, target_model = None, glossary = None, formality = None):
        if (self.loop == None):
            return {"status":1,"msg":""}
        return self.loop.run_until_complete(self.TranslateAsync(text, target_lang, source_lang, target_model, glossary, formality, False))
    async def get_translations(self, text, target_lang, source_lang = None, target_model = None, glossary = None, formality = None):
        dtype = {'appendMessage': {'type': 'message', 'message_typedef': {'events': {'type': 'message', 'message_typedef': {'fieldName': {'type': 'int', 'name': ''}, 'setPropertyOperation': {'type': 'message', 'message_typedef': {'propertyName': {'type': 'int', 'name': ''}, 'translatorFormalityModeValue': {'type': 'message', 'message_typedef': {'1':{'type':'message','message_typedef':{'1':{'type':'bytes','name':''}},'name':''}}, 'name': ''}, 'translatorGlossaryListValue': {'type': 'message', 'message_typedef': {'1':{'type':'message','message_typedef':{'1':{'type':'bytes','name':''}, '2':{'type':'bytes','name':''}},'name':''}}, 'name': ''},'translatorLanguageModelValue': {'type': 'message', 'message_typedef': {'1': {'type': 'message', 'message_typedef': {'1': {'type': 'bytes', 'name': ''}}, 'name': ''}}, 'name': ''}, 'translatorRequestedSourceLanguageValue': {'type': 'message', 'message_typedef': {'1': {'type': 'message', 'message_typedef': {'1': {'type': 'bytes', 'name': ''}}, 'name': ''}}, 'name': ''}, 'translatorRequestedTargetLanguageValue': {'type': 'message', 'message_typedef': {'1': {'type': 'message', 'message_typedef': {'1': {'type': 'bytes', 'name': ''}}, 'name': ''}}, 'name': ''}}, 'name': ''}, 'textChangeOperation': {'type': 'message', 'message_typedef': {'range': {'type': 'message', 'message_typedef': {'end': {'type': 'int', 'name': ''}}, 'name': ''}, 'text': {'type': 'bytes', 'name': ''}}, 'name': ''}, 'participantId': {'type': 'message', 'message_typedef': {'value': {'type': 'int', 'name': ''}}, 'name': ''}}, 'name': ''}, 'baseVersion': {'type': 'message', 'message_typedef': {'value': {'type': 'message', 'message_typedef': {'1': {'type': 'int', 'name': ''}}, 'name': ''}}, 'name': ''}}, 'name': ''}}

        dtype = ProtobufRemoveNames(dtype, "ParticipantRequest", True)
        lst = []
        if (formality != None):
            lst.append({"fieldName": 2, "setPropertyOperation": {"propertyName":8, "translatorFormalityModeValue":{"1":{"1":formality.encode()}}}, "participantId":{"value":2}})
        else:
            lst.append({"fieldName": 2, "setPropertyOperation": {"propertyName":8, "translatorFormalityModeValue":{"1":{}}}, "participantId":{"value":2}})
        if (type(glossary) == list):
            glosarry_lst = []
            for glossary_item in glossary:
                if (type(glossary_item) != dict or glossary_item.get("source") == None or glossary_item.get("target") == None or len(glossary_item.get("source").strip()) == 0 or len(glossary_item.get("target").strip()) == 0):
                    continue
                glosarry_lst.append({'1': glossary_item.get("source").encode(), '2': glossary_item.get("target").encode()})
            if (len(glosarry_lst) == 1):
                lst.append({'fieldName': 2, 'setPropertyOperation': {'propertyName': 10, 'translatorGlossaryListValue': {'1': glosarry_lst[0]}}, 'participantId': {'value': 2}})
            elif (len(glosarry_lst) > 1):
                lst.append({'fieldName': 2, 'setPropertyOperation': {'propertyName': 10, 'translatorGlossaryListValue': {'1': glosarry_lst}}, 'participantId': {'value': 2}})
        else:
            lst.append({'fieldName': 2, 'setPropertyOperation': {'propertyName': 10, 'translatorGlossaryListValue': {'1': []}}, 'participantId': {'value': 2}})
        lst.append({'fieldName': 2, 'setPropertyOperation': {'propertyName': 5, 'translatorRequestedTargetLanguageValue': {'1': {'1': target_lang.encode()}}}, 'participantId': {'value': 2}})
        if (source_lang == None):
            lst.append({'fieldName': 1, 'setPropertyOperation': {'propertyName': 3}, 'participantId': {'value': 2}})
        else:
            lst.append({'fieldName': 1, 'setPropertyOperation': {'propertyName': 3, 'translatorRequestedSourceLanguageValue': {'1': {'1': source_lang.encode()}}}, 'participantId': {'value': 2}})
        if (target_model != None):
            lst.append({'fieldName': 2, 'setPropertyOperation': {'propertyName': 16, 'translatorLanguageModelValue': {'1': {'1': target_model.encode()}}}, 'participantId': {'value': 2}})
        lst.append({'fieldName': 1, 'textChangeOperation': {'range': {"end":len(self.input)}, 'text': text.encode()}, 'participantId': {'value': 2}})
        translate_text = ProtobufRemoveNames({'appendMessage': {'events': lst, 'baseVersion': {'value': {'1': self.connection.bver}}}}, "ParticipantRequest")
        self.input = text
        translate = msgpackPack([msgpack.packb([2, {}, '1', msgpack.ExtType(4, bytes(blackboxprotobuf.encode_message(translate_text, dtype)))])])    
        await self.connection.send(translate)
        msgs = await self.connection.pop_message()
        if (msgs == None or msgs[3] == "OnError"):
            return None
        msgs = ProtobufAddNames(blackboxprotobuf.decode_message(msgs[3].data)[0],"ParticipantResponse")
        if msgs == None or msgs.get("confirmedMessage") == None:
            return None
        true = True
        while true:
            i = await self.connection.pop_message()
            if (i == None):
                return None
            decoded, data_type = blackboxprotobuf.decode_message(i[3].data)
            try:
                data_type['3']['message_typedef']['1']['message_typedef']['2']['message_typedef']['2']['type'] = 'bytes'
            except:
                pass
            decoded, data_type = blackboxprotobuf.decode_message(i[3].data, message_type=data_type)
            js = ProtobufAddNames(decoded, "ParticipantResponse")
            if (js.get("metaInfoMessage") != None and js.get("metaInfoMessage").get("idle") != None):
                true = False
                break
            if (js.get("publishedMessage") != None):
                if (js["publishedMessage"].get("currentVersion") != None):
                    self.connection.bver = js["publishedMessage"]["currentVersion"]["1"]["1"]
                if js["publishedMessage"].get("events") != None:
                    events = js["publishedMessage"]["events"]
                    if (type(events) == dict):
                        events = [events]
                    for evt in events:
                        if (evt.get("textChangeOperation") != None):
                            if (evt["fieldName"] == 2):
                                if (evt["textChangeOperation"].get("range") != None and evt["textChangeOperation"]["range"].get("start") != None and evt["textChangeOperation"]["range"].get("end") != None and evt["textChangeOperation"]["range"]["start"] == len(self.output) and evt["textChangeOperation"]["range"]["end"] == len(self.output)):
                                    self.output += evt["textChangeOperation"]["text"].decode()
                                else:
                                    self.output = evt["textChangeOperation"]["text"].decode()
                            elif (evt["fieldName"] == 1):
                                if (evt["textChangeOperation"].get("range") != None and evt["textChangeOperation"]["range"].get("start") != None and evt["textChangeOperation"]["range"].get("end") != None and evt["textChangeOperation"]["range"]["start"] == len(self.input) and evt["textChangeOperation"]["range"]["end"] == len(self.input)):
                                    self.input += evt["textChangeOperation"]["text"].decode()
                                else:
                                    self.input = evt["textChangeOperation"]["text"].decode()
        return self.output