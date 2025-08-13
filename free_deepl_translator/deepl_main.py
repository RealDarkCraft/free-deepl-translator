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

class Deepl:
    def __init__(self):
        self.auth_name = "free"
        self.mode = "longpolling"
        self.wss = None
        self.input = ""
        self.output = ""
        self.nego_token = None
        self.bver = 19
        self.msg = []
        self.connection = False
        self.last_error = ""
        self.OnError = False
        self.max_text_len = 0
        self.sources_langs = []
        self.target_langs = []
        self.last_status_code = 0
    def Session(self):
        self.wss = None
        self.input = ""
        self.output = ""
        self.bver = 19
        self.msg = []
        self.last_error = ""
        self.loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(target=self._start_loop, daemon=True)
        self.loop_thread.start()
        return asyncio.run(self.createInstance())
    async def SessionAsync(self):
        self.wss = None
        self.input = ""
        self.output = ""
        self.bver = 19
        self.msg = []
        self.last_error = ""
        self.loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(target=self._start_loop, daemon=True)
        self.loop_thread.start()
        return await asyncio.create_task(self.createInstance())
    def _start_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
    def _start_mainloop(self):
        asyncio.set_event_loop(self.mainloop)
        self.mainloop.run_forever()
    async def send_request(self, url, methode, data = b"", headers={}, out = "binary", can_websocket = False):
        is_websocket = (self.mode == "websocket" and can_websocket == True and methode == "post")
        if (is_websocket == False):
            async with curl_cffi.AsyncSession() as client:
                try:
                    if (methode == "get"):
                        response = await client.get(url, headers=headers, impersonate = "firefox")
                    elif (methode == "post"):
                        response = await client.post(url,data=data, headers=headers, impersonate = "firefox")
                    self.last_status_code = response.status_code
                    if (response.status_code == 200):
                        if (out == "binary"):
                            return response.content
                        elif (out == "json"):
                            return response.json()
                    return None
                except Exception as e:
                    return None
        elif (is_websocket == True):
            asyncio.run_coroutine_threadsafe(self.wss.send(data), self.loop)
    def compute_url(self, is_wss = False):
        if (is_wss == False):
            return f'https://ita-{self.auth_name}.www.deepl.com/v1/sessions?id={self.nego_token["connectionToken"]}&_={time.time_ns() // 1_000_000}'
        elif (is_wss == True):
            return f'wss://ita-{self.auth_name}.www.deepl.com/v1/sessions?id={self.nego_token["connectionToken"]}'
    
    async def TranslateAsync(self, text, target_lang, source_lang = None, target_model = None, glossary = None, formality = None):
        if self.connection == False:
            return {"status":1,"msg":"Not connected to an session (Do you forget to call \"*.Session()\" ?)"}
        elif self.connection == None:
            return {"status":1,"msg":"Invalid Session (Session might break in case of errors)"}
        if (len(text) >= self.max_text_len):
            return {"status":1,"msg":f"Text must not exceed <{self.max_text_len}> lenght"}
        if (target_lang not in self.target_langs):
            return {"status":1,"msg":f"Invalid target language <{target_lang}>"}
        if (source_lang != None and source_lang not in self.sources_langs):
            return {"status":1,"msg":f"Invalid source language <{source_lang}>"}
        try:
            trans = await asyncio.create_task(self.get_translations(text, target_lang, source_lang, target_model, glossary, formality))
        except Exception as e:
            return {"status":1,"msg":e}
        if (trans ==  ""):
            return {"status":1,"msg":""}
        elif (trans == None):
            return {"status":1,"msg":self.last_error}
        return {"status":0,"text":trans}

    def Translate(self, text, target_lang, source_lang = None, target_model = None, glossary = None, formality = None):
        if self.connection == False:
            return {"status":1,"msg":"Not connected to an session (Do you forget to call \"*.Session()\" ?)"}
        elif self.connection == None:
            return {"status":1,"msg":"Invalid Session (Session might break in case of errors)"}
        if (len(text) >= self.max_text_len):
            return {"status":1,"msg":f"Text must not exceed <{self.max_text_len}> lenght"}
        if (target_lang not in self.target_langs):
            return {"status":1,"msg":f"Invalid target language <{target_lang}>"}
        if (source_lang != None and source_lang not in self.sources_langs):
            return {"status":1,"msg":f"Invalid source language <{source_lang}>"}
        try:
            trans = asyncio.run(self.get_translations(text, target_lang, source_lang, target_model, glossary, formality))
        except Exception as e:
            return {"status":1,"msg":e}
        if (trans ==  ""):
            return {"status":1,"msg":""}
        elif (trans == None):
            return {"status":1,"msg":self.last_error}
        return {"status":0,"text":trans}
    async def listener(self):
        if (self.mode == "longpolling"):
            while True:
                res = await self.send_request(self.compute_url(), "get")
                if res is None or res == b"":
                    continue
                if res[-1] == 0x1e and res[0] == 123 and res[-2] == 125 :
                    self.msg.append(json.loads(res[:-1]))
                else:
                    data = msgpackUnpack(res)
                    data = [msgpack.unpackb(i) for i in data]
                    for i in data:
                        if len(i) >= 4 and i[3] == "OnError":
                            self.loop.call_soon_threadsafe(self.loop.stop)
                            self.connection = None
                            self.last_error = ProtobufAddNames(blackboxprotobuf.decode_message(i[4][0].data)[0],"ClientErrorInfo")["detailCode"]["value"].decode()
                            self.OnError = True
                    self.msg.append(data)
        elif (self.mode == "websocket"):
            async with curl_cffi.AsyncSession() as s:
                self.wss = await s.ws_connect(self.compute_url(True), impersonate = "firefox")
                while True:
                    res = await self.wss.recv()
                    if res is None:
                        break
                    if (res[1] == 2):
                        if res[0] == b"":
                            continue
                        if res[0][-1] == 0x1e and res[0][0] == 123 and res[0][-2] == 125:
                            self.msg.append(json.loads(res[0][:-1]))
                        else:
                            data = msgpackUnpack(res[0])
                            data = [msgpack.unpackb(i) for i in data]
                            for i in data:
                                if len(i) >= 4 and i[3] == "OnError":
                                    self.loop.call_soon_threadsafe(self.loop.stop)
                                    self.connection = None
                                    self.last_error = ProtobufAddNames(blackboxprotobuf.decode_message(i[4][0].data)[0],"ClientErrorInfo")["detailCode"]["value"].decode()
                            self.msg.append(data)
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
        if (target_model != None):
            lst.append({'fieldName': 2, 'setPropertyOperation': {'propertyName': 16, 'translatorLanguageModelValue': {'1': {'1': target_model.encode()}}}, 'participantId': {'value': 2}})
        lst.append({'fieldName': 2, 'setPropertyOperation': {'propertyName': 5, 'translatorRequestedTargetLanguageValue': {'1': {'1': target_lang.encode()}}}, 'participantId': {'value': 2}})
        if (source_lang == None):
            lst.append({'fieldName': 1, 'setPropertyOperation': {'propertyName': 3}, 'participantId': {'value': 2}})
        else:
            lst.append({'fieldName': 1, 'setPropertyOperation': {'propertyName': 3, 'translatorRequestedSourceLanguageValue': {'1': {'1': source_lang.encode()}}}, 'participantId': {'value': 2}})
        lst.append({'fieldName': 1, 'textChangeOperation': {'range': {"end":len(self.input)}, 'text': text.encode()}, 'participantId': {'value': 2}})
        translate_text = ProtobufRemoveNames({'appendMessage': {'events': lst, 'baseVersion': {'value': {'1': self.bver}}}}, "ParticipantRequest")
        self.input = text
        translate = msgpackPack([msgpack.packb([2, {}, '1', msgpack.ExtType(4, bytes(blackboxprotobuf.encode_message(translate_text, dtype)))])])    
        self.output = ""
        await asyncio.create_task(self.send_request(self.compute_url(),"post", data = translate, can_websocket = True))
        msgs = await asyncio.create_task(self.pop_message())
        if (msgs == None or msgs[0][3] == "OnError"):
            return None
        msgs = ProtobufAddNames(blackboxprotobuf.decode_message(msgs[0][3].data)[0],"ParticipantResponse")
        if msgs == None or msgs.get("confirmedMessage") == None:
            return None
        true = True
        while true:
            res_parsed = await asyncio.create_task(self.pop_message())
            if (res_parsed == None):
                return None
            for i in res_parsed:
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
                        self.bver = js["publishedMessage"]["currentVersion"]["1"]["1"]
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
                            
    async def pop_message(self, timeout = 5):
        current_time = int(time.time())
        while (len(self.msg) < 1 and (int(time.time()) < (current_time + timeout))):
            pass
        if (len(self.msg) < 1):
            return None
        return self.msg.pop()
        

    async def createInstance(self):
        url_nego = f"https://ita-{self.auth_name}.www.deepl.com/v1/sessions/negotiate?negotiateVersion=1"
        self.connection = None
        self.nego_token = await asyncio.create_task(self.send_request(url_nego,"post", out = "json"))
        if (self.nego_token == None or self.last_status_code != 200):
            return False
        self.loop.call_soon_threadsafe(lambda: asyncio.create_task(self.listener()))
        
        if (self.mode == "websocket"):
            while (self.wss == None):
                pass
        await asyncio.create_task(self.send_request(self.compute_url(),"post", data = b'{"protocol":"messagepack","version":1}\x1e', can_websocket = True))
        msg = await asyncio.create_task(self.pop_message())
        if (msg != {}):
            return False
        
        d = base64.b64decode("TpUBgKEwrFN0YXJ0U2Vzc2lvbpHHOAEIARIwCgsIASIHCA5yAwjcCwohCAIiDQgFKgkKBwoFZW4tVVMiDggSkgEJCgcKBWVuLVVTGgIQAQ==")
        await asyncio.create_task(self.send_request(self.compute_url(),"post", data = d, can_websocket = True))
        msg = await asyncio.create_task(self.pop_message())
        if (msg == None or self.OnError == True):
            return False
        typ = ProtobufAddNames(blackboxprotobuf.decode_message(msg[0][4].data)[1],"StartSessionResponse", True)
        typ["sessionToken"]["type"] = "bytes"
        self.token = ProtobufAddNames(blackboxprotobuf.decode_message(msg[0][4].data, message_type = ProtobufRemoveNames(typ, "StartSessionResponse", True))[0],"StartSessionResponse")["sessionToken"].decode()
        
        
        append_msg = msgpackPack([msgpack.packb([1, {}, None, 'AppendMessages', [self.token], ['1']])])
        await asyncio.create_task(self.send_request(self.compute_url(),"post", data = append_msg, can_websocket = True))
        get_msg = msgpackPack([msgpack.packb([4, {}, '2', 'GetMessages', [self.token, msgpack.ExtType(code=3, data=b'')]])])
        await asyncio.create_task(self.send_request(self.compute_url(),"post", data = get_msg, can_websocket = True))
        msg = await asyncio.create_task(self.pop_message())
        if (msg == None):
            return False
        if (msg[0][3] == "OnError"):
            return False
        msgdec = ProtobufAddNames(blackboxprotobuf.decode_message(msg[0][3].data)[1],"ParticipantResponse", True)
        try:
            msgdec["publishedMessage"]["message_typedef"]["events"]["message_typedef"]["setPropertyOperation"]["message_typedef"]["translatorSourceLanguagesValue"]["message_typedef"]["1"]["message_typedef"]["1"]["type"] = "bytes"
        except:
            pass
        try:
            msgdec["publishedMessage"]["message_typedef"]["events"]["message_typedef"]["setPropertyOperation"]["message_typedef"]["translatorTargetLanguagesValue"]["message_typedef"]["1"]["message_typedef"]["1"]["type"] = "bytes"
        except:
            pass
        tmp = ProtobufRemoveNames(msgdec, "ParticipantResponse", True)
        try:
            msgdec = ProtobufAddNames(blackboxprotobuf.decode_message(msg[0][3].data,message_type=tmp)[0],"ParticipantResponse")["publishedMessage"]
        except:
            return False
        self.bver = msgdec["currentVersion"]["1"]["1"]
        self.sources_langs = []
        self.target_langs = []
        for evt in msgdec["events"]:
            if evt["setPropertyOperation"]["propertyName"] == 1:
                for lang in evt["setPropertyOperation"]["translatorSourceLanguagesValue"]["1"]:
                    self.sources_langs.append(lang["1"].decode())
            if evt["setPropertyOperation"]["propertyName"] == 2:
                for lang in evt["setPropertyOperation"]["translatorTargetLanguagesValue"]["1"]:
                    self.target_langs.append(lang["1"].decode())
            elif evt["setPropertyOperation"]["propertyName"] == 14 and evt["fieldName"] == 1:
                self.max_text_len = evt["setPropertyOperation"]["translatorMaximumTextLengthValue"]["1"]    
        self.sources_langs.append("en")
        self.target_langs.append("en")
        msg = await asyncio.create_task(self.pop_message())
        if (msg == None):
            return False
        self.connection = True
        return True