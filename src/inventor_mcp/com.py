"""COM connection to Inventor, pinned to one dedicated thread.

COM objects are apartment-bound: an object obtained on one thread must not be
used from another. The MCP server is asyncio-based, so every Inventor call is
funnelled through a single worker thread that initialised COM once.
"""

from __future__ import annotations

import asyncio
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

T = TypeVar("T")

PROG_ID = "Inventor.Application"


class InventorUnavailable(RuntimeError):
    """Raised when Inventor cannot be reached."""


def _com_init() -> None:
    if sys.platform != "win32":
        return
    import pythoncom  # type: ignore[import-not-found]

    pythoncom.CoInitialize()


def describe_error(exc: BaseException) -> str:
    """Readable message for any exception, including pywintypes.com_error."""
    args = getattr(exc, "args", ())
    # com_error args: (hresult, text, excepinfo, argerror); excepinfo[2] is the description
    if type(exc).__name__ == "com_error" and len(args) >= 3:
        hresult, text, excepinfo = args[0], args[1], args[2]
        detail = excepinfo[2] if excepinfo and len(excepinfo) > 2 and excepinfo[2] else None
        msg = f"Inventor COM error {hresult & 0xFFFFFFFF:#010x}: {detail or text}"
        return msg
    return f"{type(exc).__name__}: {exc}" if not isinstance(exc, (ValueError, InventorUnavailable)) else str(exc)


class InventorSession:
    """Owns the COM thread and the cached Inventor.Application object."""

    def __init__(self, launch_if_missing: bool | None = None) -> None:
        if launch_if_missing is None:
            launch_if_missing = os.environ.get("INVENTOR_MCP_LAUNCH", "1") != "0"
        self.launch_if_missing = launch_if_missing
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="inventor-com", initializer=_com_init
        )
        self._app: Any = None

    # -- runs on the COM thread -------------------------------------------
    def _connect(self) -> Any:
        if sys.platform != "win32":
            raise InventorUnavailable(
                "Autodesk Inventor is only available on Windows. "
                "Run this MCP server on the Windows machine where Inventor is installed."
            )
        try:
            import win32com.client  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - windows only
            raise InventorUnavailable("pywin32 is not installed: pip install pywin32") from exc

        try:
            return win32com.client.GetActiveObject(PROG_ID)
        except Exception:
            if not self.launch_if_missing:
                raise InventorUnavailable(
                    "No running Inventor instance found and INVENTOR_MCP_LAUNCH=0."
                ) from None
        try:
            app = win32com.client.Dispatch(PROG_ID)
            app.Visible = True
            return app
        except Exception as exc:
            raise InventorUnavailable(f"Could not start Inventor: {exc}") from exc

    def _get_app(self) -> Any:
        if self._app is not None:
            try:
                _ = self._app.Caption  # cheap liveness probe
                return self._app
            except Exception:
                self._app = None  # Inventor was closed; reconnect below
        self._app = self._connect()
        return self._app

    def _run(self, fn: Callable[[Any], T]) -> T:
        return fn(self._get_app())

    # -- public API ---------------------------------------------------------
    async def call(self, fn: Callable[[Any], T]) -> T:
        """Run ``fn(app)`` on the COM thread and await the result."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._run, fn)

    def call_sync(self, fn: Callable[[Any], T]) -> T:
        return self._executor.submit(self._run, fn).result()
