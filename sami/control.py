"""Cooperative run cancellation over signals or protocol v1 stdin."""
from __future__ import annotations

import _thread
from contextlib import contextmanager
import json
import os
import stat
import sys
from threading import Event, Thread

from sami.events import PROTOCOL_VERSION


class RunControl:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.cancelled = Event()
        self._closed = Event()
        self._committing = False
        self.active: tuple[str, str, int, float] | None = None

    def signal(self, signum, frame) -> None:
        self.cancelled.set()
        if not self._closed.is_set():
            self.check()

    def check(self) -> None:
        if self.cancelled.is_set() and not self._committing:
            raise KeyboardInterrupt

    @contextmanager
    def publishing(self):
        """Defer cancellation while committing a result and its terminal event."""
        self._committing = True
        try:
            yield
        finally:
            self._committing = False

    def close(self) -> None:
        self._closed.set()

    def read_stdin(self) -> None:
        if os.name == "nt" and sys.stdin.isatty():
            return
        # An unbuffered duplicate avoids leaving a daemon thread holding
        # Python's buffered stdin lock when an open GUI pipe outlives the CLI.
        descriptor = os.dup(sys.stdin.fileno())
        Thread(target=self._read_commands, args=(descriptor,), daemon=True).start()

    def _read_commands(self, descriptor: int) -> None:
        with os.fdopen(descriptor, "rb", buffering=0) as stream:
            lines = (
                self._windows_pipe_lines(descriptor)
                if os.name == "nt" and stat.S_ISFIFO(os.fstat(descriptor).st_mode)
                else stream
            )
            for line in lines:
                if self._closed.is_set():
                    return
                try:
                    command = json.loads(line)
                except (ValueError, UnicodeError):
                    continue
                if (
                    isinstance(command, dict)
                    and type(command.get("protocol_version")) is int
                    and command["protocol_version"] == PROTOCOL_VERSION
                    and command.get("command") == "cancel"
                    and command.get("run_id") == self.run_id
                ):
                    self.cancelled.set()
                    _thread.interrupt_main()
                    return

    def _windows_pipe_lines(self, descriptor: int):
        """Read only available bytes so native DLL startup can access the CRT."""
        import ctypes
        from ctypes import wintypes
        import msvcrt

        peek = ctypes.WinDLL("kernel32", use_last_error=True).PeekNamedPipe
        peek.argtypes = (
            wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
        )
        peek.restype = wintypes.BOOL
        handle = msvcrt.get_osfhandle(descriptor)
        available = wintypes.DWORD()
        pending = b""
        while not self._closed.is_set():
            if not peek(handle, None, 0, None, ctypes.byref(available), None):
                return
            if not available.value:
                self._closed.wait(0.025)
                continue
            chunk = os.read(descriptor, min(available.value, 4096))
            if not chunk:
                return
            *complete, pending = (pending + chunk).split(b"\n")
            yield from complete
