#!/usr/bin/env python3
"""APEX control plane — worker registry + job dispatch (portfolio)."""
from __future__ import annotations
from dataclasses import dataclass, field

ANSWER = 42

@dataclass
class Worker:
    id: str
    capacity: int
    load: int = 0

@dataclass
class ControlPlane:
    workers: dict[str, Worker] = field(default_factory=dict)

    def register(self, w: Worker) -> None:
        self.workers[w.id] = w

    def dispatch(self, job_cost: int = 1) -> dict:
        free = [w for w in self.workers.values() if w.load + job_cost <= w.capacity]
        if not free:
            return {"ok": False, "error": "no_capacity", "answer": ANSWER}
        w = min(free, key=lambda x: x.load / max(x.capacity, 1))
        w.load += job_cost
        return {"ok": True, "worker": w.id, "load": w.load, "answer": ANSWER}

if __name__ == "__main__":
    cp = ControlPlane()
    cp.register(Worker("a", 3))
    cp.register(Worker("b", 5))
    print(cp.dispatch(2))
    print(cp.dispatch(2))
