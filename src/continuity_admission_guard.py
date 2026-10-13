"""Serialize recovery/application on one kernel without blocking unrelated kernels.

The registry owns a strong kernel reference only while admissions are active or
waiting; this supports unhashable and slotted runtime kernels without adding
persistence state or mutating their lifecycle models.
"""
from __future__ import annotations

from contextlib import contextmanager
from threading import RLock
from typing import Any, Iterator

_REGISTRY_GUARD = RLock()
_ACTIVE: dict[int, list[Any]] = {}


@contextmanager
def exclusive_kernel_admission(kernel: Any) -> Iterator[None]:
    """Hold per-kernel admission through host application and executor dispatch."""
    identity = id(kernel)
    with _REGISTRY_GUARD:
        entry = _ACTIVE.get(identity)
        if entry is None:
            entry = [kernel, RLock(), 0]
            _ACTIVE[identity] = entry
        elif entry[0] is not kernel:
            raise RuntimeError("kernel identity changed while admitting context")
        entry[2] += 1
    try:
        with entry[1]:
            yield
    finally:
        with _REGISTRY_GUARD:
            entry[2] -= 1
            if entry[2] == 0:
                del _ACTIVE[identity]
