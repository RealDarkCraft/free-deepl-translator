from __future__ import annotations
import asyncio
import time
from typing import Any, Dict, Optional

import curl_cffi
import msgpack
from curl_cffi import AsyncSession

from .deepl_logger import Logger
from .deepl_protobuf import proto_decode, proto_encode
from .deepl_msgpack import msgpackPack
from .deepl_signalr import SignalRMessageHandler


class Session:
    """Represents a SignalR DeepL session."""

    def __init__(self, proto: Dict[str, Any]):
        self.sessionVersion: int = 2
        self.verStr: str = "v2"
        self.decoded: Dict[str, Any] = proto
        self._update_from_proto(proto)

    def _update_from_proto(self, proto: Dict[str, Any]) -> None:
        self.sessionId = (
            proto["sessionId"]["value"] if proto.get("sessionId") else None
        )
        self.participantId = (
            proto["participantId"]["value"] if proto.get("participantId") else None
        )
        self.sessionToken = proto.get("sessionToken")
        self.endpoint = proto.get("signalrEndpoint")
        self.decoded = proto

    def refresh(self, proto: Dict[str, Any]) -> None:
        self._update_from_proto(proto)

    def buildQueryParameters(self) -> str:
        if self.endpoint:
            parts = self.endpoint.split("?", 1)
            return parts[1] if len(parts) > 1 else ""
        return ""


class DeeplConnection:
    """WebSocket or long-polling connection to the DeepL server."""

    def __init__(
        self,
        parent: Any,
        auth_type: str,
        mode: str,
        experimental: bool,
    ):
        self.logger = Logger(False)
        self.SignalrSession = Session({})
        self.is_handshaked: bool = False
        self.session: Optional[Any] = None
        self.parent = parent
        self.property = parent.property
        self.experiments: Optional[str] = self._fetch_experimental_feature(experimental)
        self.auth_type = auth_type
        self.config: Dict[str, Optional[str]] = {"send": None, "recv": None, "mode": None}
        self._stop_event = asyncio.Event()
        self.mode = mode
        self.nego_token: Optional[Dict] = None
        self.client: Optional[AsyncSession] = AsyncSession()
        self.conn: Optional[Any] = None
        self._recv_task: Optional[asyncio.Task] = None
        self.status: Optional[bool] = None
        self.collector: list = []
        self.waiters: Dict[str, Optional[asyncio.Event]] = {
            "handshake": None,
            "participant": None,
        }
        self._is_closing: bool = False
        self._lock = asyncio.Lock()
        self.signalR = SignalRMessageHandler(self)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _set_all_waiters(self) -> None:
        for waiter in self.waiters.values():
            if waiter is not None:
                waiter.set()

    def _fetch_experimental_feature(self, flag: bool) -> Optional[str]:
        if not flag:
            return None
        try:
            r = curl_cffi.requests.get(
                "https://experimentation.deepl.com/v2/experiments",
                impersonate="firefox",
            )
            if r.status_code != 200:
                return None
            experiments = r.json().get("experiments")
            if not experiments:
                return None
            parts = []
            for el in experiments:
                v1, v2 = el["variants"][0], el["variants"][1]
                variant_id = v2["id"] if v1["share"] < v2["share"] else v1["id"]
                parts.append(
                    f"{el['id']}.{el['name']}.{variant_id}.{el['breakout']}_"
                )
            return "_".join(parts)
        except Exception as e:
            self.logger.Error(e)
            return None

    def _build_headers(self, *, with_cookie: bool = True) -> Dict[str, str]:
        headers: Dict[str, str] = {"origin": "https://www.deepl.com"}
        if with_cookie and self.experiments is not None:
            headers["cookie"] = f"releaseGroups={self.experiments}"
        return headers

    def compute_url(self) -> str:
        query_param = self.SignalrSession.buildQueryParameters()
        if query_param:
            query_param += "&"
        token = self.nego_token["connectionToken"]
        if self.mode == "websocket":
            return (
                f"wss://ita-{self.auth_type}.www.deepl.com"
                f"/{self.SignalrSession.verStr}/sessions"
                f"?{query_param}id={token}"
            )
        ts = time.time_ns() // 1_000_000
        return (
            f"https://ita-{self.auth_type}.www.deepl.com"
            f"/{self.SignalrSession.verStr}/sessions"
            f"?{query_param}id={token}&_={ts}"
        )

    # ------------------------------------------------------------------
    # Handshake / ping
    # ------------------------------------------------------------------

    async def Handshake(self, msg: Dict) -> None:
        if msg != {}:
            self.status = False
            return
        self.is_handshaked = True
        await asyncio.sleep(0)
        await self.send_ping()
        self.config = {"send": "0", "recv": "1", "mode": "invoke"}
        await self.property.Function_StartSessionResponse(self.SignalrSession.decoded)

    async def send_ping(self) -> None:
        try:
            await self.send(msgpackPack([[6]]))
            self.logger.Info("Ping sent")
        except Exception as e:
            self.logger.Error(e)

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def ws_connect(self, url: str) -> None:
        if self.mode == "websocket":
            headers = {
                "host": f"ita-{self.auth_type}.www.deepl.com",
                "Sec-WebSocket-Extensions": "permessage-deflate; client_max_window_bits",
                **self._build_headers(),
            }
            self.conn = await self.client.ws_connect(
                url, headers=headers, impersonate="firefox"
            )
        self._recv_task = asyncio.create_task(self._recv_loop())

    async def _recv_loop(self) -> None:
        if self.client is None:
            self._set_all_waiters()
            return
        try:
            if self.mode == "websocket":
                try:
                    async for msg in self.conn:
                        if self._is_closing or not self.client:
                            self._set_all_waiters()
                            break
                        try:
                            await self.signalR.format_res(msg)
                        except Exception as e:
                            self.logger.Error(e)
                except Exception as e:
                    self.logger.Error(e)
                    self.property.OnError = True
                    self.property.OnErrorLast = "Connection closed abruptly"
                self.status = False

            elif self.mode == "longpolling":
                while not self._stop_event.is_set() and not self._is_closing:
                    if not self.client:
                        break
                    try:
                        res = await self.client.get(
                            self.compute_url(),
                            headers=self._build_headers(),
                            impersonate="firefox",
                        )
                        if res.status_code == 200 and res.content:
                            await self.signalR.format_res(res.content)
                    except Exception as e:
                        self.logger.Error(e)
                self.status = False
        except Exception as e:
            self.logger.Error(e)
        finally:
            self._set_all_waiters()
            self.conn = None

    async def send(self, data: bytes) -> None:
        if self._is_closing or not self.client or self.status is False:
            self._set_all_waiters()
            return
        fail = False
        try:
            async with self._lock:
                if self.mode == "websocket" and self.conn is not None:
                    await self.conn.send(data)
                elif self.mode == "longpolling":
                    r = await self.client.post(
                        self.compute_url(),
                        headers=self._build_headers(),
                        data=data,
                        impersonate="firefox",
                    )
                    fail = r.status_code != 200
        except Exception as e:
            fail = True
            self.logger.Error(e)
        if fail:
            await self.close()

    async def _wait_for_tasks(self, timeout: float = 3.0) -> None:
        if not self.collector:
            return
        try:
            await asyncio.wait_for(
                asyncio.gather(*self.collector, return_exceptions=True),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            for task in self.collector:
                if not task.done():
                    task.cancel()
        finally:
            self.collector.clear()

    async def close(self) -> None:
        if self._is_closing:
            return
        self._is_closing = True
        self.status = False
        self._stop_event.set()

        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
            try:
                await asyncio.wait_for(self._recv_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        await self._wait_for_tasks()

        for task in self.collector:
            if not task.done():
                task.cancel()
        if self.collector:
            await asyncio.gather(*self.collector, return_exceptions=True)
        self.collector.clear()

        if self.mode == "websocket" and self.conn is not None:
            try:
                await asyncio.wait_for(self.conn.close(), timeout=1.0)
            except Exception as e:
                self.logger.Error(e)
            self.conn = None

        async with self._lock:
            if self.client is not None:
                try:
                    await asyncio.wait_for(self.client.close(), timeout=2.0)
                except Exception as e:
                    self.logger.Error(e)
                self.client = None

    # ------------------------------------------------------------------
    # Main connect
    # ------------------------------------------------------------------

    async def deepl_connect(self, session: Dict[str, Any]) -> None:
        self.session = session
        if self.status is True:
            return
        self._is_closing = False

        if self.client is None:
            self.client = AsyncSession()

        headers = {
            "content-type": "application/x-protobuf",
            "host": f"ita-{self.auth_type}.www.deepl.com",
            "origin": "https://www.deepl.com",
        }
        try:
            resp = await self.client.post(
                f"https://ita-{self.auth_type}.www.deepl.com"
                f"/{self.SignalrSession.verStr}/startSession",
                headers=headers,
                data=proto_encode(session, "StartSessionRequest"),
                impersonate="firefox",
            )
            if resp.status_code != 200:
                self.logger.Error(f"startSession HTTP {resp.status_code}")
                self.status = False
                return
        except Exception as e:
            self.logger.Error(e)
            self.status = False
            return

        self.SignalrSession.refresh(
            proto_decode(resp.content, "StartSessionResponse")[0]
        )

        self.is_handshaked = False
        self.status = None
        self.property.OnError = False

        query_param = self.SignalrSession.buildQueryParameters()
        if query_param:
            query_param += "&"
        url_nego = (
            f"https://ita-{self.auth_type}.www.deepl.com"
            f"/{self.SignalrSession.verStr}/sessions/negotiate"
            f"?{query_param}negotiateVersion=1"
        )
        res = await self.client.post(
            url_nego, headers=self._build_headers(), impersonate="firefox"
        )
        if res.status_code != 200:
            self.status = False
            return
        self.nego_token = res.json()

        self.waiters["handshake"] = asyncio.Event()
        await self.ws_connect(self.compute_url())
        asyncio.create_task(
            self.send(b'{"protocol":"messagepack","version":1}\x1e')
        )
        await self.waiters["handshake"].wait()
        if self.property.OnError:
            self.status = False
