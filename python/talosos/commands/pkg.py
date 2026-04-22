
"""`talos pkg` subcommands: create, list."""

from typing import Dict, List, Optional, Tuple

import argparse

import json

import re

import sys
from pathlib import Path

from ..workspace import (
    MANIFEST_FILENAME, Workspace, load_or_init_workspace, load_workspace,
)

_PKG_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")

_CMAKE_PREAMBLE = """\
cmake_minimum_required(VERSION 3.22)
project({pkg} VERSION {version} LANGUAGES CXX)

# TALOSOS_ROOT is exported by setup.bash to point at the install prefix.
# The find_package call below picks it up without the policy noise.
if(POLICY CMP0144)
  cmake_policy(SET CMP0144 NEW)
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(TalosOS REQUIRED)
"""

_CMAKE_BODY_EMPTY = """\

# Add your executables here and install them so `talos run {pkg} <exe>` finds
# them. Example:
#
#   add_executable({pkg}_node src/{pkg}_node.cc)
#   target_link_libraries({pkg}_node PRIVATE TalosOS::talosos)
#   install(TARGETS {pkg}_node RUNTIME DESTINATION lib/${{PROJECT_NAME}})
"""

_CMAKE_BODY_WITH_NODE = """\

add_executable({pkg}_node src/{pkg}_node.cc)
target_link_libraries({pkg}_node PRIVATE TalosOS::talosos)
install(TARGETS {pkg}_node RUNTIME DESTINATION lib/${{PROJECT_NAME}})
"""

_MANIFEST_TEMPLATE = """\
name: {pkg}
version: {version}
description: {desc}
depends:
  - talosos
executables:{executables}
"""

_GITIGNORE = """\
/build/
/install/
/logs/
"""

_NODE_TEMPLATE = """\
#include "talosos/logging.h"
#include "talosos/node.h"

int main(int argc, char** argv) {{
  talos::Init(argc, argv);
  auto node = talos::Node::Create("{pkg}_node");
  TALOS_INFO("hello from {pkg}_node");
  node->Spin();
  return 0;
}}
"""

def register_create(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("name", help="New package name (snake_case)")
    parser.add_argument("--workspace", type=Path,
                          help="Path to a workspace directory (defaults to auto-discover)")
    parser.add_argument("--description", default="")
    parser.add_argument("--version", default="0.0.1")
    parser.add_argument("--with-node", action="store_true",
                          help="Generate a skeleton src/<pkg>_node.cc too")
    parser.set_defaults(func=_do_create)

def register_list(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(func=_do_list)

def _resolve_ws(args: argparse.Namespace, *, auto_init: bool = False) -> Workspace:
    start = args.workspace if getattr(args, "workspace", None) else None
    if auto_init:
        return load_or_init_workspace(start)
    return load_workspace(start)

def _do_create(args: argparse.Namespace) -> int:
    if not _PKG_NAME_RE.match(args.name):
        print(f"error: invalid package name {args.name!r}; expected snake_case",
                file=sys.stderr)
        return 2
    # ROS1-style ergonomics: `mkdir -p ws/src && cd ws/src && talos pkg create ...`
    # should succeed without a prior `touch .talos_ws`.
    ws = _resolve_ws(args, auto_init=True)
    ws.src_dir.mkdir(parents=True, exist_ok=True)

    pkg_dir = ws.src_dir / args.name
    if pkg_dir.exists():
        print(f"error: {pkg_dir} already exists", file=sys.stderr)
        return 2

    for sub in ("src", "include", "launch", "msg"):
        (pkg_dir / sub).mkdir(parents=True, exist_ok=True)

    executables_block = (
        f"\n  - {args.name}_node" if args.with_node else " []"
    )
    (pkg_dir / MANIFEST_FILENAME).write_text(
        _MANIFEST_TEMPLATE.format(
            pkg=args.name,
            version=args.version,
            desc=args.description or f"{args.name} package",
            executables=executables_block,
        ),
        encoding="utf-8",
    )

    body = (_CMAKE_BODY_WITH_NODE if args.with_node else _CMAKE_BODY_EMPTY)
    cmake_text = (_CMAKE_PREAMBLE + body).format(
        pkg=args.name, version=args.version)
    (pkg_dir / "CMakeLists.txt").write_text(cmake_text, encoding="utf-8")
    (pkg_dir / ".gitignore").write_text(_GITIGNORE, encoding="utf-8")

    if args.with_node:
        (pkg_dir / "src" / f"{args.name}_node.cc").write_text(
            _NODE_TEMPLATE.format(pkg=args.name), encoding="utf-8")

    print(f"created package '{args.name}' at {pkg_dir}")
    return 0

def _do_list(args: argparse.Namespace) -> int:
    ws = _resolve_ws(args)
    pkgs = ws.find_packages()

    if args.json:
        out = [
            {
                "name": pkg.name,
                "path": str(pkg.path),
                "version": pkg.version,
                "description": pkg.description,
                "executables": pkg.executables,
                "depends": pkg.depends,
            }
            for pkg in pkgs
        ]
        print(json.dumps(out, indent=2))
        return 0

    if not pkgs:
        print("(no packages found)")
        return 0

    if not args.verbose:
        for pkg in pkgs:
            print(pkg.name)
        return 0

    width = max(len(pkg.name) for pkg in pkgs)
    for pkg in pkgs:
        print(f"{pkg.name.ljust(width)}  {pkg.version:<10} {pkg.path}")
    return 0
