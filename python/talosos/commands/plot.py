"""`talos plot` — live matplotlib plot of a scalar field from a topic."""


import argparse
import collections
import signal
import sys
import threading
import time

from ..echo_stream import iter_samples
from ..messages import decode, field_path, resolve_type


_DEFAULT_FIELD_BY_TYPE = {
    "Float32": "data",
    "Float64": "data",
    "Int8":    "data", "Int16":  "data",
    "Int32":   "data", "Int64":  "data",
    "UInt8":   "data", "UInt16": "data",
    "UInt32":  "data", "UInt64": "data",
}


def register(p: argparse.ArgumentParser) -> None:
    p.add_argument("topic")
    p.add_argument("--type", dest="msg_type", required=True,
                    help="Message type (e.g. Float64, Imu, PoseStamped)")
    p.add_argument("--field", default=None,
                    help="Dotted field path to plot (default: `data` for scalars)")
    p.add_argument("--history", type=int, default=200,
                    help="Number of points to keep on screen (default 200)")
    p.add_argument("--title", default=None)
    p.set_defaults(func=_do_plot)


def _do_plot(args) -> int:
    try:
        msg_cls = resolve_type(args.msg_type)
    except KeyError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2

    field = args.field
    if not field:
        field = _DEFAULT_FIELD_BY_TYPE.get(args.msg_type)
    if not field:
        print(f"error: --field is required for type {args.msg_type}",
                file=sys.stderr)
        return 2

    try:
        import matplotlib
        matplotlib.use("TkAgg" if _has_backend("TkAgg") else
                        "QtAgg" if _has_backend("QtAgg") else
                        "Agg")
        import matplotlib.pyplot as plt
    except ImportError as ex:
        print(f"error: matplotlib is required for `talos plot`: {ex}",
                file=sys.stderr)
        return 2

    xs: collections.deque = collections.deque(maxlen=args.history)
    ys: collections.deque = collections.deque(maxlen=args.history)

    fig, ax = plt.subplots()
    ax.set_title(args.title or f"{args.topic} / {args.msg_type}.{field}")
    ax.set_xlabel("sample")
    ax.set_ylabel(field)
    line, = ax.plot([], [])

    stop = threading.Event()
    lock = threading.Lock()

    def reader():
        try:
            for sample in iter_samples(args.topic):
                if stop.is_set():
                    return
                try:
                    msg = decode(args.msg_type, sample.payload)
                    value = float(field_path(msg, field))
                except Exception as ex:  # noqa: BLE001
                    print(f"decode error: {ex}", file=sys.stderr)
                    continue
                with lock:
                    xs.append(sample.seq)
                    ys.append(value)
        finally:
            stop.set()

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    def on_sigint(signum, frame):
        stop.set()
        plt.close("all")

    signal.signal(signal.SIGINT, on_sigint)

    plt.ion()
    plt.show(block=False)
    try:
        while not stop.is_set():
            with lock:
                if xs:
                    line.set_data(list(xs), list(ys))
                    ax.relim()
                    ax.autoscale_view()
            try:
                fig.canvas.draw_idle()
                fig.canvas.flush_events()
            except Exception:
                break
            time.sleep(0.05)
            if not plt.fignum_exists(fig.number):
                break
    finally:
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
