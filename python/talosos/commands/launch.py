"""`talos launch` — run a YAML launch file orchestrating multiple nodes."""

from typing import Dict, List, Optional, Set, Tuple

import argparse
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..workspace import Workspace, load_workspace

# ANSI palette reused across concurrent streams.
_COLORS = [
    "\x1b[36m",  # cyan
    "\x1b[33m",  # yellow
    "\x1b[35m",  # magenta
    "\x1b[32m",  # green
    "\x1b[34m",  # blue
    "\x1b[31m",  # red
    "\x1b[96m",  # bright cyan
    "\x1b[93m",  # bright yellow
]
_RESET = "\x1b[0m"

@dataclass
class NodeSpec:
    package: str
    executable: str
    name: str
    args: List[str] = field(default_factory=list)
    env: dict = field(default_factory=dict)

def register(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="Path to a .launch.yaml file "
                          "(or <package> <file> if two positional args given)")
    parser.add_argument("target2", nargs="?", default=None,
                          help="Optional launch file name when `target` is a package")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--dry-run", action="store_true",
                          help="Print what would be spawned and exit")
    parser.set_defaults(func=_do_launch)

def _resolve_launch_path(args: argparse.Namespace) -> Path:
    # 1) direct path
    direct = Path(args.target)
    if direct.is_file():
        return direct.resolve()

    ws: Optional[Workspace] = None
    try:
        ws = load_workspace(args.workspace)
    except Exception:
        pass

    if args.target2:
        # `talos launch <package> <file>`
        if ws is None:
            raise SystemExit(f"error: no workspace to resolve package '{args.target}'")
        pkg = ws.find_package(args.target)
        if pkg is None:
            raise SystemExit(f"error: package '{args.target}' not found")
        for d in [pkg.path / "launch",
                    ws.install_dir / "share" / pkg.name / "launch"]:
            cand = d / args.target2
            if cand.is_file():
                return cand.resolve()
        raise SystemExit(
            f"error: launch file '{args.target2}' not found under package '{pkg.name}'")

    # Single target — look across every workspace package.
    if ws:
        for pkg in ws.find_packages():
            for d in [pkg.path / "launch",
                        ws.install_dir / "share" / pkg.name / "launch"]:
                cand = d / args.target
                if cand.is_file():
                    return cand.resolve()

    raise SystemExit(f"error: launch target '{args.target}' not found")

def _parse_nodes(path: Path) -> List[NodeSpec]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: launch file must be a YAML mapping")
    raw_nodes = data.get("nodes") or []
    if not isinstance(raw_nodes, list):
        raise SystemExit(f"{path}: 'nodes' must be a list")
    out: List[NodeSpec] = []
    seen = set()
    for idx, n in enumerate(raw_nodes):
        if not isinstance(n, dict):
            raise SystemExit(f"{path}: nodes[{idx}] must be a mapping")
        if "package" not in n or "executable" not in n:
            raise SystemExit(
                f"{path}: nodes[{idx}] requires 'package' and 'executable'")
        name = str(n.get("name") or n["executable"])
        if name in seen:
            raise SystemExit(f"{path}: duplicate node name '{name}'")
        seen.add(name)
        out.append(NodeSpec(
            package=str(n["package"]),
            executable=str(n["executable"]),
            name=name,
            args=[str(a) for a in (n.get("args") or [])],
            env={str(k): str(v) for k, v in (n.get("env") or {}).items()},
        ))
    return out

def _resolve_executable(ws: Workspace, spec: NodeSpec) -> Path:
    candidates = [
        ws.install_dir / "lib" / spec.package / spec.executable,
        ws.install_dir / "bin" / spec.executable,
        ws.build_dir / spec.package / spec.executable,
    ]
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return c
    raise SystemExit(
        f"error: executable '{spec.executable}' not built for package "
        f"'{spec.package}'. Run `talos build` first.")

def _stream_output(name: str, color: str, stream, write_lock: threading.Lock):
    while True:
        line = stream.readline()
        if not line:
            break
        with write_lock:
            sys.stdout.write(f"{color}[{name}]{_RESET} {line.decode('utf-8', 'replace')}")
            sys.stdout.flush()

def _do_launch(args: argparse.Namespace) -> int:
    path = _resolve_launch_path(args)
    nodes = _parse_nodes(path)
    if not nodes:
        print("(no nodes in launch file)")
        return 0

    ws = load_workspace(args.workspace)
    resolved = [(n, _resolve_executable(ws, n)) for n in nodes]

    if args.dry_run:
        for n, exe in resolved:
            print(f"{n.name}: {exe} {' '.join(n.args)}")
        return 0

    # Environment shared by all children — adds workspace install to LD_LIBRARY_PATH.
    base_env = os.environ.copy()
    ws_lib = str(ws.install_dir / "lib")
    existing_lib = base_env.get("LD_LIBRARY_PATH", "")
    base_env["LD_LIBRARY_PATH"] = (
        ws_lib if not existing_lib else ws_lib + os.pathsep + existing_lib
    )

    write_lock = threading.Lock()
    procs: List[Tuple[NodeSpec, subprocess.Popen, threading.Thread, threading.Thread]] = []

    def spawn_all():
        for idx, (spec, exe) in enumerate(resolved):
            color = _COLORS[idx % len(_COLORS)]
            env = base_env.copy()
            env.update(spec.env)
            print(f"{color}[{spec.name}]{_RESET} starting: {exe} {' '.join(spec.args)}")
            try:
                p = subprocess.Popen(
                    [str(exe), *spec.args],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=env,
                )
            except OSError as ex:
                print(f"error: failed to spawn {spec.name}: {ex}", file=sys.stderr)
                return False
            t = threading.Thread(
                target=_stream_output,
                args=(spec.name, color, p.stdout, write_lock),
                daemon=True,
            )
            t.start()
            procs.append((spec, p, t, t))  # dummy second thread placeholder
        return True

    if not spawn_all():
        _terminate_all(procs)
        return 2

    shutdown = threading.Event()

    def on_signal(signum, frame):
        shutdown.set()

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    rc = 0
    try:
        # Poll until a child dies or we get a signal.
        while not shutdown.is_set():
            time.sleep(0.1)
            alive = False
            for spec, p, _t, _t2 in procs:
                if p.poll() is None:
                    alive = True
                elif not getattr(p, "_talos_exit_logged", False):
                    p._talos_exit_logged = True
                    print(f"[{spec.name}] exited code={p.returncode}")
                    if p.returncode != 0:
                        rc = p.returncode or 1
            if not alive:
                break
    finally:
        _terminate_all(procs)

    # Drain any remaining output.
    for _spec, _p, t, _t2 in procs:
        t.join(timeout=1.0)
    return rc

def _terminate_all(procs):
    import time as _time
    for spec, p, *_ in procs:
        if p.poll() is None:
            try:
                p.send_signal(signal.SIGINT)
            except ProcessLookupError:
                pass

    deadline = _time.time() + 3.0
    while _time.time() < deadline:
        if all(p.poll() is not None for _s, p, *_ in procs):
            return
        _time.sleep(0.1)

    for spec, p, *_ in procs:
        if p.poll() is None:
            try:
                p.terminate()
            except ProcessLookupError:
                pass

    deadline = _time.time() + 2.0
    while _time.time() < deadline:
        if all(p.poll() is not None for _s, p, *_ in procs):
            return
        _time.sleep(0.1)

    for spec, p, *_ in procs:
        if p.poll() is None:
            try:
                p.kill()
            except ProcessLookupError:
                pass
