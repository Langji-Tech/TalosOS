#!/usr/bin/env python3
"""Class-form example — same shape as examples/cpp/class_demo.

Run the node:
    python3 class_demo.py                 # publish at 2Hz (default)
    python3 class_demo.py --hz 5

Run the client in another terminal:
    python3 class_demo.py --client
    python3 class_demo.py --client --reset-after 4

Wire layout and topic / service names are identical to the C++ demo, so you
can freely cross-run (C++ node + Python client, and vice versa)."""

from __future__ import annotations

import argparse
import sys
import threading
import time
from dataclasses import dataclass
from typing import ClassVar, Optional

from talosos.cdr import CdrReader
from talosos.messages import Int64
from talosos.runtime import Node, init, ok
from talosos.runtime import _CdrWriter, _WRITERS_BY_CLASS  # type: ignore


# --- Service types (match the C++ class_demo::GetCountResponse wire layout) ---

@dataclass
class Empty:
    # One pad byte — same convention the C++ side uses for std_msgs/Empty.
    pad: int = 0
    TYPE_NAME: ClassVar[str] = "Empty"

    @classmethod
    def read(cls, r: CdrReader) -> "Empty":
        return cls(pad=r.u8())


@dataclass
class GetCountResponse:
    count: int = 0
    TYPE_NAME: ClassVar[str] = "GetCountResponse"

    @classmethod
    def read(cls, r: CdrReader) -> "GetCountResponse":
        return cls(count=r.i64())


_WRITERS_BY_CLASS[Empty] = lambda w, v: w.u8(v.pad)
_WRITERS_BY_CLASS[GetCountResponse] = lambda w, v: w.i64(v.count)


# --- Node class: holds publishers / subscriptions / services as members ---

class ChatterNode:
    """Periodically publishes an Int64 counter and exposes /reset + /get_count."""

    def __init__(self, node_name: str = "chatter_class_node",
                 publish_hz: float = 2.0) -> None:
        self._hz = publish_hz
        self._count = 0
        self._count_lock = threading.Lock()
        self._running = threading.Event()
        self._worker: Optional[threading.Thread] = None

        self.node = Node.create(node_name)

        # Publishers / subscriptions / services are stored as members so they
        # live as long as the object does.
        self.chatter_pub = self.node.advertise("chatter", Int64)
        self.reset_sub = self.node.subscribe("reset", Empty, self._on_reset)
        self.count_svc = self.node.advertise_service(
            "get_count", Empty, GetCountResponse, self._on_get_count)

        print(f"ChatterNode ready: publish /{self.chatter_pub.key}, "
              f"subscribe /{self.reset_sub.key}, service /{self.count_svc._raw.key}")

    # ---- callbacks ----

    def _on_reset(self, msg: Empty) -> None:
        with self._count_lock:
            prev, self._count = self._count, 0
        print(f"reset received: count was {prev}")

    def _on_get_count(self, req: Empty) -> GetCountResponse:
        with self._count_lock:
            current = self._count
        return GetCountResponse(count=current)

    # ---- lifecycle ----

    def start(self) -> None:
        if self._running.is_set():
            return
        self._running.set()
        self._worker = threading.Thread(target=self._publish_loop, daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self._running.clear()
        if self._worker:
            self._worker.join(timeout=2.0)
            self._worker = None

    def _publish_loop(self) -> None:
        period = 1.0 / self._hz if self._hz > 0 else 0.5
        while self._running.is_set() and ok():
            with self._count_lock:
                value, self._count = self._count, self._count + 1
            self.chatter_pub.publish(Int64(data=value))
            time.sleep(period)


# --- Simple paired client ---

class ChatterClient:
    def __init__(self) -> None:
        self.node = Node.create("chatter_class_client")
        self.sub = self.node.subscribe(
            "/chatter_class_node/chatter", Int64,
            lambda m: print(f"got count = {m.data}"))
        self.reset_pub = self.node.advertise(
            "/chatter_class_node/reset", Empty)
        self.client = self.node.create_service_client(
            "/chatter_class_node/get_count", Empty, GetCountResponse)

    def run(self, reset_after: int) -> int:
        time.sleep(0.4)   # let discovery settle
        for t in range(1, 40 + 1):
            time.sleep(0.5)
            if t == reset_after:
                print("publishing /reset")
                self.reset_pub.publish(Empty())
            if t == reset_after + 4:
                resp = self.client.call(Empty(), timeout_ms=2000)
                if resp is None:
                    print("get_count timed out", file=sys.stderr)
                    return 1
                print(f"service /get_count -> {resp.count}")
                return 0
        return 0


# --- main() ---

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hz", type=float, default=2.0)
    parser.add_argument("--client", action="store_true",
                          help="Run the companion client instead of the node")
    parser.add_argument("--reset-after", type=int, default=5)
    args = parser.parse_args()

    init()

    if args.client:
        return ChatterClient().run(args.reset_after)

    chatter = ChatterNode(publish_hz=args.hz)
    chatter.start()
    try:
        chatter.node.spin()
    finally:
        chatter.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
