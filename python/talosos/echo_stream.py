"""Wraps the C++ talosos_tool topic-echo as an iterator of decoded bytes.

Running zenoh from Python would pull a heavy dependency; instead we shell out
to the already-installed `talosos_tool` binary with --no-truncate and parse
its stdout, which is one line per sample:

    #0 key=<key> bytes=<N> data_hex=<HEX>
"""

from typing import Iterator, Optional

import os
import re
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_LINE_RE = re.compile(
    r"^#(?P<seq>\d+)\s+key=(?P<key>\S+)\s+bytes=(?P<n>\d+)\s+data_hex=(?P<hex>[0-9a-fA-F]+)"
)

def find_tool() -> str:
    exe = shutil.which("talosos_tool")
    if exe:
        return exe
    here = Path(sys.argv[0]).resolve().parent
    cand = here / "talosos_tool"
    if cand.is_file() and os.access(cand, os.X_OK):
        return str(cand)
    raise SystemExit(
        "error: talosos_tool not on PATH. Source the TalosOS setup first.")

@dataclass
class Sample:
    seq: int
    key: str
    payload: bytes

def iter_samples(key: str,
                 *,
                 count: int = 0,
                 extra_args: Optional[list] = None) -> Iterator[Sample]:
    """Yield Sample objects until the subprocess exits or the caller breaks."""
    cmd = [find_tool(), "topic-echo", key.lstrip("/"), "--no-truncate"]
    if count > 0:
        cmd += ["--count", str(count)]
    if extra_args:
        cmd += list(extra_args)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=1,
        text=True,
    )
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            m = _LINE_RE.match(line.strip())
            if not m:
                continue
            yield Sample(
                seq=int(m.group("seq")),
                key=m.group("key"),
                payload=bytes.fromhex(m.group("hex")),
            )
    finally:
        if proc.poll() is None:
            try:
                proc.send_signal(signal.SIGINT)
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=1.0)
            except ProcessLookupError:
                pass
