"""`talos topic` subcommands — thin wrapper around the talosos_tool binary."""

from typing import Dict, Iterable, List, Optional, Set, Tuple

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

_TOOL_BIN = "talosos_tool"

def _find_tool() -> str:
    exe = shutil.which(_TOOL_BIN)
    if exe:
        return exe
    # Fallback: look next to the currently running `talos` entry.
    here = Path(sys.argv[0]).resolve().parent
    cand = here / _TOOL_BIN
    if cand.is_file() and os.access(cand, os.X_OK):
        return str(cand)
    print(f"error: {_TOOL_BIN} not found on PATH. Did you `source setup.bash`?",
          file=sys.stderr)
    sys.exit(2)

def _add_network_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--mode", choices=["peer", "client", "router"])
    p.add_argument("--connect", action="append", default=[])
    p.add_argument("--listen", action="append", default=[])
    p.add_argument("--no-multicast", dest="multicast", action="store_false",
                    default=True)

def _network_tool_args(args: argparse.Namespace) -> List[str]:
    out: List[str] = []
    if getattr(args, "mode", None):
        out += ["--mode", args.mode]
    for ep in getattr(args, "connect", []) or []:
        out += ["--connect", ep]
    for ep in getattr(args, "listen", []) or []:
        out += ["--listen", ep]
    if getattr(args, "multicast", True) is False:
        out += ["--no-multicast"]
    return out

def _normalize_topic(name: str) -> str:
    """`/foo/bar` -> `foo/bar`; leading slashes stripped so it matches the
    zenoh key convention used by the runtime."""
    return name.lstrip("/")

def _run_tool(argv: Iterable[str], env: Optional[dict] = None) -> int:
    """运行 talosos_tool，优雅处理 Ctrl-C：
    子进程（C++）与父进程（Python）会同时收到 SIGINT。让子进程自己清理
    并退出，父这边不再抛 KeyboardInterrupt traceback。
    """
    cmd = [_find_tool(), *argv]
    proc = subprocess.Popen(cmd, env=env or os.environ.copy())
    try:
        return proc.wait()
    except KeyboardInterrupt:
        # 子进程已经收到 SIGINT；给它几秒收尾，必要时升级到 terminate/kill。
        try:
            return proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                return proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                return proc.wait()

# ---- echo ----

def _register_echo(p: argparse.ArgumentParser) -> None:
    p.add_argument("topic")
    p.add_argument("--count", type=int, default=0,
                    help="Stop after receiving N messages (0 = unbounded)")
    _add_network_options(p)
    p.set_defaults(func=_do_echo)

def _do_echo(args) -> int:
    tool_args = ["topic-echo", _normalize_topic(args.topic)]
    if args.count:
        tool_args += ["--count", str(args.count)]
    tool_args += _network_tool_args(args)
    return _run_tool(tool_args)

# ---- hz / bw ----

def _register_hz(p: argparse.ArgumentParser) -> None:
    p.add_argument("topic")
    p.add_argument("--count", type=int, default=0,
                    help="Stop after N reports (0 = unbounded)")
    p.add_argument("--window", type=float, default=1.0,
                    help="Averaging window in seconds")
    p.add_argument("--report-period", type=float, default=1.0,
                    help="How often to emit a measurement (seconds)")
    _add_network_options(p)
    p.set_defaults(func=_do_hz)

def _register_bw(p: argparse.ArgumentParser) -> None:
    p.add_argument("topic")
    p.add_argument("--count", type=int, default=0)
    p.add_argument("--window", type=float, default=1.0)
    p.add_argument("--report-period", type=float, default=1.0)
    _add_network_options(p)
    p.set_defaults(func=_do_bw)

def _measure_args(args, cmd: str) -> List[str]:
    tool_args = [cmd, _normalize_topic(args.topic),
                   "--window", str(args.window),
                   "--report-period", str(args.report_period)]
    if args.count:
        tool_args += ["--count", str(args.count)]
    tool_args += _network_tool_args(args)
    return tool_args

def _do_hz(args) -> int:
    return _run_tool(_measure_args(args, "topic-hz"))

def _do_bw(args) -> int:
    return _run_tool(_measure_args(args, "topic-bw"))

# ---- pub ----

def _register_pub(p: argparse.ArgumentParser) -> None:
    p.add_argument("topic")
    payload = p.add_mutually_exclusive_group(required=True)
    payload.add_argument("--hex", help="Payload as hex string")
    payload.add_argument("--utf8", help="Payload as UTF-8 string")
    p.add_argument("--count", type=int, default=1,
                    help="Number of messages (default 1, 0 = infinite)")
    p.add_argument("--rate", type=float, default=1.0,
                    help="Publish rate in Hz when --count != 1")
    _add_network_options(p)
    p.set_defaults(func=_do_pub)

def _do_pub(args) -> int:
    tool_args = ["topic-pub", _normalize_topic(args.topic)]
    if args.hex:
        tool_args += ["--hex", args.hex]
    else:
        tool_args += ["--utf8", args.utf8]
    tool_args += ["--count", str(args.count), "--rate", str(args.rate)]
    tool_args += _network_tool_args(args)
    return _run_tool(tool_args)

# ---- list / info ----

def _register_list(p: argparse.ArgumentParser) -> None:
    p.add_argument("--timeout-ms", type=int, default=500,
                    help="Discovery timeout in milliseconds (default 500)")
    p.add_argument("--verbose", action="store_true",
                    help="Also show advertising nodes per topic")
    _add_network_options(p)
    p.set_defaults(func=_do_list)

def _register_info(p: argparse.ArgumentParser) -> None:
    p.add_argument("topic")
    p.add_argument("--timeout-ms", type=int, default=500)
    _add_network_options(p)
    p.set_defaults(func=_do_info)

def _as_topic_name(key: str) -> str:
    """Render a zenoh key in ROS-style (with a leading slash) for display."""
    return key if key.startswith("/") else "/" + key

def _collect_list(args, kind: str) -> List[Tuple[str, str, List[str]]]:
    """Returns list of (topic_key, type_name, [nodes]).

    type_name is "" when the publisher didn't broadcast one (pre-1.0 peer
    or non-TalosOS publisher).
    """
    tool_args = [f"{kind}-list", "--timeout-ms", str(args.timeout_ms)]
    tool_args += _network_tool_args(args)
    proc = subprocess.run([_find_tool(), *tool_args],
                            capture_output=True, text=True,
                            env=os.environ.copy())
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        return []
    out: List[Tuple[str, str, List[str]]] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        key = _as_topic_name(parts[0])
        if len(parts) >= 3:
            type_name = parts[1]
            nodes = parts[2].split(",") if parts[2] else []
        elif len(parts) == 2:
            type_name = ""
            nodes = parts[1].split(",") if parts[1] else []
        else:
            type_name = ""
            nodes = []
        out.append((key, type_name, nodes))
    return out

def _do_list(args) -> int:
    entries = _collect_list(args, "topic")
    if not entries:
        return 0
    if args.verbose:
        # key \t type \t nodes  — 三列对齐便于肉眼和脚本消费
        for key, tname, nodes in entries:
            print(f"{key}\t{tname or '-'}\t{','.join(nodes)}")
    else:
        for key, _t, _n in entries:
            print(key)
    return 0

def _do_info(args) -> int:
    target = _as_topic_name(_normalize_topic(args.topic))
    entries = _collect_list(args, "topic")
    for key, tname, nodes in entries:
        if key == target:
            print(f"topic:       {key}")
            print(f"type:        {tname or '(unknown)'}")
            print(f"publishers:  {len(nodes)}")
            for n in nodes:
                print(f"  - {n}")
            return 0
    print(f"(no publishers found for {target})", file=sys.stderr)
    return 1

def register(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="subcommand")
    _register_echo(sub.add_parser("echo", help="Print incoming messages"))
    _register_hz(sub.add_parser("hz", help="Measure message rate"))
    _register_bw(sub.add_parser("bw", help="Measure bandwidth"))
    _register_pub(sub.add_parser("pub", help="Publish a message"))
    _register_list(sub.add_parser("list", help="List topics with publishers"))
    _register_info(sub.add_parser("info", help="Inspect a specific topic"))
