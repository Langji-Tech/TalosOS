#!/usr/bin/env python3
"""10-topic imshow viewer for the TalosOS image_bench publisher.

Subscribes to /bench/image_0 .. /bench/image_{N-1} and renders each in a
2×5 (or auto-sized) matplotlib grid. Each cell shows:

  * the decoded PNG
  * the latency of the most recent frame (now - header.stamp)
  * a running avg/p99 computed from the last W frames

Usage:
    python3 image_bench_viz.py                 # 10 topics, /bench/image_*
    python3 image_bench_viz.py --topics 4
    python3 image_bench_viz.py --topic-prefix /camera/ --topics 6
    python3 image_bench_viz.py --no-display    # headless, stats only
"""

from __future__ import annotations

import argparse
import io
import math
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from talosos.messages import CompressedImage, Image
from talosos.runtime import Node, init, ok


@dataclass
class TopicLatency:
    topic: str
    last_frame: object = None              # np.ndarray most-recent decoded
    last_latency_ms: float = 0.0
    samples: deque = field(default_factory=lambda: deque(maxlen=300))
    bytes_seen: int = 0
    frames_seen: int = 0

    def push(self, latency_ms: float, size: int) -> None:
        self.last_latency_ms = latency_ms
        self.samples.append(latency_ms)
        self.bytes_seen += size
        self.frames_seen += 1


def now_ns() -> int:
    return time.time_ns()


def decode_image(msg) -> object:
    import numpy as np
    if isinstance(msg, CompressedImage):
        import matplotlib.image as mpimage
        return mpimage.imread(io.BytesIO(bytes(msg.data)))
    # raw Image
    enc = msg.encoding.lower()
    data = np.frombuffer(bytes(msg.data), dtype=np.uint8)
    if enc in ("mono8", "8uc1"):
        return data.reshape(msg.height, msg.width)
    ch = {"rgb8": 3, "bgr8": 3, "rgba8": 4, "bgra8": 4}.get(enc, 3)
    arr = data.reshape(msg.height, msg.width, ch)
    if enc.startswith("bgr"):
        arr = arr[..., list(reversed(range(min(3, ch)))) +
                    ([3] if ch == 4 else [])]
    return arr


def percentile(samples: deque, p: float) -> float:
    if not samples:
        return 0.0
    s = sorted(samples)
    idx = max(0, min(len(s) - 1, int(p * (len(s) - 1))))
    return s[idx]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--topics", type=int, default=10)
    ap.add_argument("--topic-prefix", default="/bench/image_")
    ap.add_argument("--type", default="CompressedImage",
                    choices=["CompressedImage", "Image"])
    ap.add_argument("--no-display", action="store_true",
                    help="Skip imshow; still prints per-topic stats")
    ap.add_argument("--duration", type=float, default=0.0,
                    help="Stop after N seconds (0 = forever)")
    ap.add_argument("--report-every", type=float, default=2.0)
    args = ap.parse_args()

    msg_cls = CompressedImage if args.type == "CompressedImage" else Image

    init()
    node = Node.create("image_bench_viz")

    entries = [TopicLatency(topic=f"{args.topic_prefix}{i}")
                 for i in range(args.topics)]
    lock = threading.Lock()

    def make_cb(entry: TopicLatency):
        def _cb(msg):
            sent_ns = msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
            lat_ms = (now_ns() - sent_ns) / 1e6
            try:
                arr = decode_image(msg)
            except Exception:  # noqa: BLE001
                arr = None
            with lock:
                entry.last_frame = arr
                entry.push(lat_ms, len(msg.data))
        return _cb

    for e in entries:
        node.subscribe(e.topic, msg_cls, make_cb(e))

    # ---- periodic text report ----
    stop = threading.Event()

    def reporter():
        next_report = time.monotonic() + args.report_every
        while not stop.is_set():
            time.sleep(0.1)
            if time.monotonic() < next_report:
                continue
            with lock:
                print(f"\n=== image_bench_viz latency report "
                      f"(window={args.report_every}s) ===")
                print(f"{'topic':<20} {'msgs':>6} {'last':>8} {'mean':>8} "
                      f"{'p50':>8} {'p90':>8} {'p99':>8} {'max':>8}  (ms)")
                total = 0
                all_samples = []
                for e in entries:
                    s = list(e.samples)
                    mean = sum(s) / len(s) if s else 0.0
                    p50 = percentile(e.samples, 0.5)
                    p90 = percentile(e.samples, 0.9)
                    p99 = percentile(e.samples, 0.99)
                    mx = max(s) if s else 0.0
                    print(f"{e.topic:<20} {e.frames_seen:>6} "
                          f"{e.last_latency_ms:>8.2f} {mean:>8.2f} "
                          f"{p50:>8.2f} {p90:>8.2f} {p99:>8.2f} {mx:>8.2f}")
                    total += e.frames_seen
                    all_samples.extend(s)
                    e.frames_seen = 0
                    e.bytes_seen = 0
                if all_samples:
                    all_samples.sort()
                    mean = sum(all_samples) / len(all_samples)
                    def _p(q):
                        return all_samples[min(len(all_samples) - 1,
                                                int(q * (len(all_samples) - 1)))]
                    print(f"{'ALL':<20} {total:>6} {'':>8} {mean:>8.2f} "
                          f"{_p(0.5):>8.2f} {_p(0.9):>8.2f} {_p(0.99):>8.2f} "
                          f"{all_samples[-1]:>8.2f}")
            next_report += args.report_every

    threading.Thread(target=reporter, daemon=True).start()

    # ---- GUI ----
    if args.no_display:
        deadline = (time.monotonic() + args.duration) if args.duration > 0 else float("inf")
        try:
            while ok() and time.monotonic() < deadline:
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        stop.set()
        return 0

    import matplotlib
    matplotlib.use("TkAgg" if _has_backend("TkAgg") else
                     "QtAgg" if _has_backend("QtAgg") else "Agg")
    import matplotlib.pyplot as plt

    cols = min(5, args.topics)
    rows = math.ceil(args.topics / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 3, rows * 3))
    axes = [axes] if args.topics == 1 else axes.flatten()
    ims = [None] * args.topics
    for ax in axes[args.topics:]:
        ax.axis("off")
    for i, ax in enumerate(axes[:args.topics]):
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(entries[i].topic, fontsize=8)

    plt.tight_layout()
    plt.ion()
    plt.show(block=False)

    deadline = (time.monotonic() + args.duration) if args.duration > 0 else float("inf")
    try:
        while ok() and time.monotonic() < deadline and plt.fignum_exists(fig.number):
            with lock:
                for i in range(args.topics):
                    arr = entries[i].last_frame
                    if arr is None:
                        continue
                    if ims[i] is None:
                        ims[i] = axes[i].imshow(arr)
                    else:
                        ims[i].set_data(arr)
                    axes[i].set_xlabel(
                        f"last={entries[i].last_latency_ms:.1f} ms  "
                        f"p99={percentile(entries[i].samples, 0.99):.1f} ms",
                        fontsize=7)
            fig.canvas.draw_idle()
            fig.canvas.flush_events()
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    stop.set()
    plt.close("all")
    return 0


def _has_backend(name: str) -> bool:
    try:
        import matplotlib
        matplotlib.use(name, force=True)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
