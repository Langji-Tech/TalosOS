
"""`talos build` — per-package CMake out-of-source build + install."""

from typing import Dict, List, Optional, Tuple

import argparse

import os

import subprocess

import sys
from pathlib import Path

from ..workspace import Workspace, load_workspace

def register(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("packages", nargs="*",
                          help="Package(s) to build; default is all")
    parser.add_argument("--package", dest="packages_opt", action="append",
                          default=[],
                          help="Alias for positional packages")
    parser.add_argument("--jobs", "-j", type=int, default=0,
                          help="Parallel jobs (passed to cmake --build -j)")
    parser.add_argument("--build-type", default="Release",
                          help="CMAKE_BUILD_TYPE (default: Release)")
    parser.add_argument("--workspace", type=Path)
    parser.set_defaults(func=_do_build)

def _select_packages(ws: Workspace, names: List[str]):
    all_pkgs = ws.find_packages()
    if not names:
        return all_pkgs
    by_name = {p.name: p for p in all_pkgs}
    missing = [n for n in names if n not in by_name]
    if missing:
        print(f"error: unknown package(s): {', '.join(missing)}", file=sys.stderr)
        return None
    return [by_name[n] for n in names]

def _do_build(args: argparse.Namespace) -> int:
    ws = load_workspace(args.workspace)
    names = list(args.packages) + list(args.packages_opt)
    selected = _select_packages(ws, names)
    if selected is None:
        return 2
    if not selected:
        print("(no packages to build)")
        return 0

    ws.build_dir.mkdir(parents=True, exist_ok=True)
    ws.install_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    prefix_paths = [str(ws.install_dir)]
    if env.get("CMAKE_PREFIX_PATH"):
        prefix_paths.append(env["CMAKE_PREFIX_PATH"])
    env["CMAKE_PREFIX_PATH"] = os.pathsep.join(prefix_paths)

    for pkg in selected:
        pkg_build = ws.build_dir / pkg.name
        pkg_build.mkdir(parents=True, exist_ok=True)

        configure = [
            "cmake",
            "-S", str(pkg.path),
            "-B", str(pkg_build),
            f"-DCMAKE_INSTALL_PREFIX={ws.install_dir}",
            f"-DCMAKE_BUILD_TYPE={args.build_type}",
            "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        ]
        print(f"[build] ({pkg.name}) configure")
        rc = subprocess.run(configure, env=env).returncode
        if rc != 0:
            return rc

        compile_cmd = ["cmake", "--build", str(pkg_build)]
        if args.jobs > 0:
            compile_cmd += ["-j", str(args.jobs)]
        print(f"[build] ({pkg.name}) compile")
        rc = subprocess.run(compile_cmd, env=env).returncode
        if rc != 0:
            return rc

        print(f"[build] ({pkg.name}) install")
        rc = subprocess.run(
            ["cmake", "--install", str(pkg_build)], env=env).returncode
        if rc != 0:
            return rc

    print(f"[build] done ({len(selected)} package(s))")
    return 0
