
"""`talos run` — launch a built package executable with workspace paths set."""

from typing import Dict, List, Optional, Tuple

import argparse

import os

import sys
from pathlib import Path

from ..workspace import Workspace, load_workspace

def register(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("package", help="Package that owns the executable")
    parser.add_argument("executable", help="Installed executable name")
    parser.add_argument("args", nargs=argparse.REMAINDER,
                          help="Extra args forwarded to the executable")
    parser.add_argument("--workspace", type=Path)
    parser.set_defaults(func=_do_run)

def _candidates(ws: Workspace, package: str, executable: str) -> List[Path]:
    return [
        ws.install_dir / "lib" / package / executable,
        ws.install_dir / "bin" / executable,
        ws.build_dir / package / executable,
    ]

def _do_run(args: argparse.Namespace) -> int:
    ws = load_workspace(args.workspace)
    candidates = _candidates(ws, args.package, args.executable)
    exe = next((c for c in candidates if c.is_file() and os.access(c, os.X_OK)),
                 None)
    if exe is None:
        print(f"error: executable '{args.executable}' not found for package "
                f"'{args.package}'.", file=sys.stderr)
        print("  searched:", file=sys.stderr)
        for cand in candidates:
            print(f"    {cand}", file=sys.stderr)
        print("  tip: run `talos build` first.", file=sys.stderr)
        return 2

    env = os.environ.copy()
    ws_lib = str(ws.install_dir / "lib")
    existing = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = (
        ws_lib if not existing else ws_lib + os.pathsep + existing
    )

    cmd = [str(exe)] + list(args.args or [])
    os.execvpe(cmd[0], cmd, env)
    return 0  # os.execvpe does not return on success
