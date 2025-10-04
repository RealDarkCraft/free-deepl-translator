import asyncio
from curl_cffi import AsyncSession
import time
import json
from .deepl_protobuf import ProtobufRemoveNames, ProtobufAddNames
from .deepl_msgpack import msgpackPack, msgpackUnpack
import base64
import msgpack
import blackboxprotobuf

class DeeplConnection:
    def __init__(self, auth_type="free", mode="longpolling"):
        self.auth_type = auth_type
        self.config = {}
        self._stop_event = asyncio.Event()
        self.mode = mode
        self.nego_token = None
        self.recv_messages = []
        self.client = AsyncSession()
        self.conn = None
        self._recv_task = None
        self.status = None
        self.OnError = False
        self.OnErrorLast = ""
    async def format_res(self, res):
        if res[-1] == 0x1e and res[0] == 123 and res[-2] == 125:
            return json.loads(res[:-1])
        data = msgpackUnpack(res)
        data = [msgpack.unpackb(i) for i in data]
        return_data = []
        for i in data:
            if len(i) >= 4 and i[3] == "OnError":
                self.OnErrorLast = ProtobufAddNames(blackboxprotobuf.decode_message(i[4][0].data)[0],"ClientErrorInfo")["detailCode"]["value"].decode()
                await self.close()
                self.status = False
                self.OnError = True
                return_data.append(i)
            elif (i[0] == 6):
                await self.send(msgpackPack([msgpack.packb([6])]))
            else:
                return_data.append(i)
        return return_data
    async def ws_connect(self, url: str):
        self.conn = await self.client.ws_connect(url, impersonate="firefox")
        self._recv_task = asyncio.create_task(self._recv_loop())
    async def _recv_loop(self):
        try:
            if (self.mode == "websocket"):
                async for msg in self.conn:
                    data = await self.format_res(msg)
                    if (type(data) == dict):
                        self.recv_messages.append(data)
                    else:
                        for elem in data:
                            self.recv_messages.append(elem)
                self.status = False
            elif (self.mode == "longpolling"):
                while not self._stop_event.is_set():
                    res = await self.client.get(self.compute_url(), impersonate = "firefox")
                    if (res.status_code == 200):
                        data = await self.format_res(res.content)
                        if (type(data) == dict):
                            self.recv_messages.append(data)
                        else:
                            for elem in data:
                                self.recv_messages.append(elem)
                self.status = False
        except Exception:
            pass
        finally:
            self.conn = None

    async def send(self, data):
        if self.mode == "websocket" and self.conn is not None:
            await self.conn.send(data)
        elif self.mode == "longpolling":
            await self.client.post(self.compute_url(), data=data, impersonate = "firefox")
    async def close(self):
        self._stop_event.set()
        if (self.mode == "websocket"):
            if self.conn is not None:
                await self.conn.close()
        elif (self.mode == "longpolling"):
            self.conn = None
        if self._recv_task is not None and self.mode == "longpolling":
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
        await self.client.close()

    async def pop_message(self, timeout=5):
        start = time.time()
        while time.time() - start < timeout:
            if self.recv_messages:
                return self.recv_messages.pop(0)
            await asyncio.sleep(0.05)
        return None

    def compute_url(self):
        if self.mode == "websocket":
            return f'wss://ita-{self.auth_type}.www.deepl.com/v1/sessions?id={self.nego_token["connectionToken"]}'
        return f'https://ita-{self.auth_type}.www.deepl.com/v1/sessions?id={self.nego_token["connectionToken"]}&_={time.time_ns() // 1_000_000}'

    async def deepl_connect(self):
        if (self.status == True):
            return
        self.status = False
        self.OnError = False
        url_nego = f"https://ita-{self.auth_type}.www.deepl.com/v1/sessions/negotiate?negotiateVersion=1"
        res = await self.client.post(url_nego, impersonate="firefox")
        if res.status_code != 200:
            return False
        self.nego_token = res.json()

        await self.ws_connect(self.compute_url())
        await self.send(b'{"protocol":"messagepack","version":1}\x1e')
        msg = await self.pop_message()
        if (msg != {}):
            return
        d = base64.b64decode("TpUBgKEwrFN0YXJ0U2Vzc2lvbpHHOAEIARIwCgsIASIHCA5yAwjcCwohCAIiDQgFKgkKBwoFZW4tVVMiDggSkgEJCgcKBWVuLVVTGgIQAQ==")
        await self.send(d)
        msg = await self.pop_message()
        if (msg == None or self.OnError == True):
            return
        typ = ProtobufAddNames(blackboxprotobuf.decode_message(msg[4].data)[1],"StartSessionResponse", True)
        typ["sessionToken"]["type"] = "bytes"
        self.token = ProtobufAddNames(blackboxprotobuf.decode_message(msg[4].data, message_type = ProtobufRemoveNames(typ, "StartSessionResponse", True))[0],"StartSessionResponse")["sessionToken"].decode()
        
        
        append_msg = msgpackPack([msgpack.packb([1, {}, None, 'AppendMessages', [self.token], ['1']])])
        await self.send(append_msg)
        get_msg = msgpackPack([msgpack.packb([4, {}, '2', 'GetMessages', [self.token, msgpack.ExtType(code=3, data=b'')]])])
        await self.send(get_msg)
        msg = await self.pop_message()
        if (msg == None):
            return
        if (msg[3] == "OnError"):
            return
        msgdec = ProtobufAddNames(blackboxprotobuf.decode_message(msg[3].data)[1],"ParticipantResponse", True)
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
            msgdec = ProtobufAddNames(blackboxprotobuf.decode_message(msg[3].data,message_type=tmp)[0],"ParticipantResponse")["publishedMessage"]
        except:
            return
        self.bver = msgdec["currentVersion"]["1"]["1"]
        self.config["source_langs"] = []
        self.config["target_langs"] = []
        self.config["maximum_text_length"] = 0
        for evt in msgdec["events"]:
            if evt["setPropertyOperation"]["propertyName"] == 1:
                for lang in evt["setPropertyOperation"]["translatorSourceLanguagesValue"]["1"]:
                    self.config["source_langs"].append(lang["1"].decode())
            if evt["setPropertyOperation"]["propertyName"] == 2:
                for lang in evt["setPropertyOperation"]["translatorTargetLanguagesValue"]["1"]:
                    self.config["target_langs"].append(lang["1"].decode())
            elif evt["setPropertyOperation"]["propertyName"] == 14 and evt["fieldName"] == 1:
                self.config["maximum_text_length"] = evt["setPropertyOperation"]["translatorMaximumTextLengthValue"]["1"]    
        self.config["source_langs"].append("en")
        self.config["target_langs"].append("en")
        msg = await self.pop_message()
        if (msg == None):
            return
        self.status = True
