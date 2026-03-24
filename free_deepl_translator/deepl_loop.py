import asyncio
import threading
from typing import Any, Coroutine, Optional, TypeVar

T = TypeVar("T")


class DeeplLoop:
    """Manages a dedicated asyncio loop in a daemon thread."""

    def __init__(self, parent: Any):
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self._init()

    def _init(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self.thread.start()

    def _run_event_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_forever()
        finally:
            self.loop.close()

    def _is_alive(self) -> bool:
        return bool(self.loop and self.thread and self.thread.is_alive())

    def run(self, coro: Coroutine[Any, Any, T], default: T = None) -> T:
        """Executes a coroutine synchronously from the calling thread."""
        if self._is_alive():
            future = asyncio.run_coroutine_threadsafe(coro, self.loop)
            return future.result()
        return default

    async def aRun(self, coro: Coroutine[Any, Any, T], default: T = None) -> T:
        """Runs a coroutine from an existing async context."""
        if not self._is_alive():
            return default
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return await asyncio.wrap_future(future)

    def destroy(self) -> None:
        """Stop the asyncio loop."""
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)

    def tryJoin(self) -> None:
        """Wait until the end of the thread."""
        if self.thread:
            try:
                self.thread.join()
            except Exception:
                pass
            self.thread = None
