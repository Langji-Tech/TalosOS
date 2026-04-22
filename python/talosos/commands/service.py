
"""`talos service` subcommands — thin wrapper around talosos_tool."""

from typing import Dict, List, Optional, Tuple

import argparse

import os

import subprocess

import sys

from .topic import (
    _add_network_options, _as_topic_name, _collect_list, _find_tool,
    _network_tool_args, _normalize_topic,
)

def _register_call(p: argparse.ArgumentParser) -> None:
    p.add_argument("service", help="Service key (e.g. /add_two_ints)")
    payload = p.add_mutually_exclusive_group(required=True)
    payload.add_argument("--hex", help="Request payload as hex")
    payload.add_argument("--utf8", help="Request payload as UTF-8 string")
    p.add_argument("--timeout-ms", type=int, default=3000)
    _add_network_options(p)
    p.set_defaults(func=_do_call)

def _register_list(p: argparse.ArgumentParser) -> None:
    p.add_argument("--timeout-ms", type=int, default=500)
    p.add_argument("--verbose", action="store_true")
    _add_network_options(p)
    p.set_defaults(func=_do_list)

def _register_info(p: argparse.ArgumentParser) -> None:
    p.add_argument("service")
    p.add_argument("--timeout-ms", type=int, default=500)
    _add_network_options(p)
    p.set_defaults(func=_do_info)

def _do_call(args) -> int:
    tool_args = ["service-call", _normalize_topic(args.service)]
    if args.hex:
        tool_args += ["--hex", args.hex]
    else:
        tool_args += ["--utf8", args.utf8]
    tool_args += ["--timeout-ms", str(args.timeout_ms)]
    tool_args += _network_tool_args(args)
    # 与 topic._run_tool 同样的 Ctrl-C 处理，避免 Python 抛 traceback。
    proc = subprocess.Popen([_find_tool(), *tool_args], env=os.environ.copy())
    try:
        return proc.wait()
    except KeyboardInterrupt:
        try:
            return proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                return proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                return proc.wait()

def _do_list(args) -> int:
    entries = _collect_list(args, "service")
    for key, tname, nodes in entries:
        if args.verbose:
            print(f"{key}\t{tname or '-'}\t{','.join(nodes)}")
        else:
            print(key)
    return 0

def _do_info(args) -> int:
    target = _as_topic_name(_normalize_topic(args.service))
    for key, tname, nodes in _collect_list(args, "service"):
        if key == target:
            print(f"service:   {key}")
            if tname:
                print(f"type:      {tname}")
            print(f"providers: {len(nodes)}")
            for n in nodes:
                print(f"  - {n}")
            return 0
    print(f"(no providers found for {target})", file=sys.stderr)
    return 1

def register(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="subcommand")
    _register_call(sub.add_parser("call", help="Invoke a service once"))
    _register_list(sub.add_parser("list", help="List active services"))
    _register_info(sub.add_parser("info", help="Inspect a specific service"))
