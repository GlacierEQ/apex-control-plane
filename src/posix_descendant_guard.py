"""Linux adopted-child guard for direct CLI worker subprocesses only.

A child that calls setsid and closes stdio can survive process-group checks.
PR_SET_CHILD_SUBREAPER makes orphaned grandchildren become our children.
Do not interpret this as macOS, Windows, or universal kernel containment.
"""
from __future__ import annotations

import os
import signal
import sys
import time


class LinuxAdoptedDescendants:
    def __init__(self) -> None:
        self.enabled = False
        self._libc = None
        self._previous = 0

    @staticmethod
    def _children() -> set[int]:
        path = f"/proc/self/task/{os.getpid()}/children"
        try:
            with open(path, encoding="ascii") as stream:
                return {int(pid) for pid in stream.read().split()}
        except FileNotFoundError:
            # Some constrained procfs mounts omit /task/*/children.
            found = set()
            with os.scandir("/proc") as entries:
                for item in entries:
                    if not item.name.isdecimal():
                        continue
                    try:
                        with open(f"/proc/{item.name}/stat", encoding="ascii") as stream:
                            stat = stream.read()
                        if int(stat.rsplit(") ", 1)[-1].split()[1]) == os.getpid():
                            found.add(int(item.name))
                    except (OSError, ValueError, IndexError):
                        continue
            return found

    def arm(self) -> bool:
        if sys.platform != "linux":
            return False
        import ctypes
        try:
            # Never adopt pre-existing unrelated subprocesses.
            if self._children():
                return False
            libc = ctypes.CDLL(None, use_errno=True)
            prev = ctypes.c_int()
            if libc.prctl(37, ctypes.byref(prev), 0, 0, 0) != 0:
                return False
            # A pre-existing subreaper belongs to another runtime boundary.
            # Never adopt/kill its descendants or alter its lifecycle state.
            if prev.value != 0:
                return False
            if libc.prctl(36, 1, 0, 0, 0) != 0:
                return False
        except (OSError, ValueError, AttributeError):
            return False
        self._libc = libc
        self._previous = prev.value
        self.enabled = True
        return True

    def finish(self, direct_pid: int | None, timeout: float = 1.0) -> tuple[bool, bool]:
        """After direct-child wait, terminate/reap newly adopted descendants.

        Adopted PIDs remain owned by us until waitpid, preventing reuse while
        signaling. Do not signal any process that is not our child.
        """
        if not self.enabled:
            return False, False
        detected = unresolved = False
        deadline = time.monotonic() + timeout
        try:
            while True:
                adopted = self._children()
                adopted.discard(direct_pid)
                if not adopted:
                    break
                detected = True
                for pid in adopted:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    except OSError:
                        unresolved = True
                    try:
                        os.waitpid(pid, os.WNOHANG)
                    except ChildProcessError:
                        pass
                    except OSError:
                        unresolved = True
                if time.monotonic() >= deadline:
                    unresolved = True
                    break
                time.sleep(0.02)
        except (OSError, ValueError):
            unresolved = True
        finally:
            if self._libc.prctl(36, self._previous, 0, 0, 0) != 0:
                unresolved = True
            self.enabled = False
        return detected, unresolved
