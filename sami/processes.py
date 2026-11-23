"""Portable process supervision for owned child processes."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from typing import Set

# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------

_IS_WINDOWS = sys.platform == "win32"

try:
    import psutil as _psutil  # type: ignore
    _HAS_PSUTIL = True
except ImportError:
    _psutil = None  # type: ignore[assignment]
    _HAS_PSUTIL = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_alive(pid: int) -> bool:
    """Return True if the process *pid* is currently running.

    Uses ``psutil.pid_exists`` on Windows when psutil is available, otherwise
    falls back to ``os.kill(pid, 0)`` on all platforms.
    """
    if _IS_WINDOWS and _HAS_PSUTIL:
        return _psutil.pid_exists(pid)  # type: ignore[union-attr]
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we can't signal it (different owner).
        return True
    except OSError:
        return False


def kill_tree(pid: int, *, timeout: float = 5.0) -> None:
    """Terminate *pid* and all its descendants.

    On Linux/macOS: sends SIGTERM to the process group (or the process itself
    if it has no dedicated group), waits *timeout/2* seconds, then sends
    SIGKILL if the process is still alive.

    On Windows: runs ``taskkill /F /T /PID <pid>`` which terminates the whole
    process tree atomically.  Falls back to ``os.kill(pid, signal.SIGTERM)``
    if *taskkill* is unavailable or fails.

    Silently ignores ``ProcessLookupError`` and ``PermissionError`` — the
    process may have already exited.  Never raises.
    """
    try:
        if _IS_WINDOWS:
            _kill_tree_windows(pid)
        else:
            _kill_tree_posix(pid, timeout=timeout)
    except (ProcessLookupError, PermissionError):
        pass
    except Exception:  # noqa: BLE001 — never raise from a cleanup helper
        pass


def find_child_pids_by_name(name: str) -> Set[int]:
    """Return PIDs of direct children of the current process named *name*.

    Uses ``psutil`` when available.  On Linux, falls back to scanning
    ``/proc/<pid>/status`` for the ``PPid`` field.  Returns an empty set on
    Windows if psutil is not installed.
    """
    if _HAS_PSUTIL:
        return _find_children_psutil(name)
    if not _IS_WINDOWS:
        return _find_children_proc(name)
    return set()


# ---------------------------------------------------------------------------
# OwnedProcesses context manager
# ---------------------------------------------------------------------------

class OwnedProcesses:
    """Thread-safe tracker that kills all registered pids on exit.

    Usage::

        with OwnedProcesses() as procs:
            p = subprocess.Popen(...)
            procs.add(p.pid)
            ...
        # All registered processes are killed here.
    """

    def __init__(self) -> None:
        self._pids: Set[int] = set()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def add(self, pid: int) -> None:
        """Register *pid* as an owned process."""
        with self._lock:
            self._pids.add(pid)

    def discard(self, pid: int) -> None:
        """Unregister *pid* (no-op if not registered)."""
        with self._lock:
            self._pids.discard(pid)

    # ------------------------------------------------------------------
    # Termination
    # ------------------------------------------------------------------

    def kill_all(self, *, timeout: float = 5.0) -> None:
        """Kill all currently registered processes."""
        with self._lock:
            pids = set(self._pids)
        for pid in pids:
            kill_tree(pid, timeout=timeout)

    # ------------------------------------------------------------------
    # Context-manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "OwnedProcesses":
        return self

    def __exit__(self, *_: object) -> None:
        self.kill_all()


# ---------------------------------------------------------------------------
# Private helpers — POSIX
# ---------------------------------------------------------------------------

def _kill_tree_posix(pid: int, *, timeout: float) -> None:
    """SIGTERM → wait → SIGKILL on POSIX."""
    try:
        pgid = os.getpgid(pid)
        use_pgroup = pgid != os.getpgid(os.getpid())  # has its own group?
    except (ProcessLookupError, PermissionError, AttributeError):
        use_pgroup = False

    def _term() -> None:
        if use_pgroup:
            try:
                os.killpg(pgid, signal.SIGTERM)
                return
            except (ProcessLookupError, PermissionError):
                pass
        os.kill(pid, signal.SIGTERM)

    def _kill() -> None:
        if use_pgroup:
            try:
                os.killpg(pgid, signal.SIGKILL)
                return
            except (ProcessLookupError, PermissionError):
                pass
        os.kill(pid, signal.SIGKILL)

    try:
        _term()
    except (ProcessLookupError, PermissionError):
        return  # already gone

    # Wait up to timeout/2 for voluntary exit.
    half = max(0.05, timeout / 2.0)
    import time
    deadline = time.monotonic() + half
    while time.monotonic() < deadline:
        if not is_alive(pid):
            return
        time.sleep(0.05)

    # Still alive — escalate.
    try:
        _kill()
    except (ProcessLookupError, PermissionError):
        pass


# ---------------------------------------------------------------------------
# Private helpers — Windows
# ---------------------------------------------------------------------------

def _kill_tree_windows(pid: int) -> None:
    """Use taskkill /F /T on Windows; fall back to os.kill."""
    try:
        result = subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            return
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    # Fall back.
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass


# ---------------------------------------------------------------------------
# Private helpers — child-process discovery
# ---------------------------------------------------------------------------

def _find_children_psutil(name: str) -> Set[int]:
    """Find direct children named *name* via psutil."""
    found: Set[int] = set()
    try:
        current = _psutil.Process()  # type: ignore[union-attr]
        for child in current.children(recursive=False):
            try:
                if child.name() == name:
                    found.add(child.pid)
            except (_psutil.NoSuchProcess, _psutil.AccessDenied):  # type: ignore[union-attr]
                pass
    except Exception:  # noqa: BLE001
        pass
    return found


def _find_children_proc(name: str) -> Set[int]:
    """Find direct children named *name* by scanning /proc (Linux only)."""
    found: Set[int] = set()
    my_pid = os.getpid()
    try:
        entries = os.listdir("/proc")
    except OSError:
        return found
    for entry in entries:
        if not entry.isdigit():
            continue
        status_path = f"/proc/{entry}/status"
        try:
            with open(status_path, "r", encoding="utf-8", errors="replace") as fh:
                ppid: int | None = None
                proc_name: str | None = None
                for line in fh:
                    if line.startswith("PPid:"):
                        try:
                            ppid = int(line.split(":", 1)[1].strip())
                        except ValueError:
                            pass
                    elif line.startswith("Name:"):
                        proc_name = line.split(":", 1)[1].strip()
                    if ppid is not None and proc_name is not None:
                        break
            if ppid == my_pid and proc_name == name:
                found.add(int(entry))
        except OSError:
            pass
    return found
