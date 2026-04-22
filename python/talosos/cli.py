"""Top-level dispatcher for the `talos` CLI."""

from typing import Optional, Sequence

import argparse
import sys

from . import __version__
from .commands import build as cmd_build
from .commands import launch as cmd_launch
from .commands import pkg as cmd_pkg
from .commands import plot as cmd_plot
from .commands import rqt as cmd_rqt
from .commands import run as cmd_run
from .commands import service as cmd_service
from .commands import topic as cmd_topic
from .commands import viz as cmd_viz

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="talos",
        description="TalosOS command-line interface",
    )
    parser.add_argument("--version", action="version",
                          version=f"talos {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    # pkg
    pkg_parser = subparsers.add_parser("pkg", help="Package management")
    pkg_sub = pkg_parser.add_subparsers(dest="subcommand")
    cmd_pkg.register_create(pkg_sub.add_parser(
        "create", help="Create a new package skeleton"))
    cmd_pkg.register_list(pkg_sub.add_parser(
        "list", help="List packages in the current workspace"))
    pkg_parser.set_defaults(func=_require_subcommand("pkg"))

    # build
    cmd_build.register(subparsers.add_parser(
        "build", help="Build workspace packages"))

    # run
    cmd_run.register(subparsers.add_parser(
        "run", help="Run a package executable"))

    # topic / service (P5)
    topic_parser = subparsers.add_parser("topic", help="Topic inspection tools")
    cmd_topic.register(topic_parser)
    topic_parser.set_defaults(func=_require_subcommand("topic"))

    service_parser = subparsers.add_parser("service", help="Service inspection tools")
    cmd_service.register(service_parser)
    service_parser.set_defaults(func=_require_subcommand("service"))

    # launch (P5)
    cmd_launch.register(subparsers.add_parser(
        "launch", help="Run a multi-process launch file"))

    # plot / viz / rqt (P6)
    cmd_plot.register(subparsers.add_parser(
        "plot", help="Live matplotlib plot of a topic field"))
    cmd_viz.register(subparsers.add_parser(
        "viz", help="Live visualizer (image/scan/cloud/marker/pose/tf)"))
    cmd_rqt.register(subparsers.add_parser(
        "rqt", help="PyQt5 shell hosting plot/viz panels"))

    return parser

def _require_subcommand(name: str):
    def handler(args):
        print(f"error: `talos {name}` requires a subcommand", file=sys.stderr)
        return 2
    return handler

def _stub(name: str, phase: str):
    def handler(args):
        print(f"talos {name}: not implemented yet (scheduled for {phase})",
                file=sys.stderr)
        return 2
    return handler

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        # 兜底：子命令没捕到的 Ctrl-C 在这里被吃掉，退出码沿 POSIX 惯例
        # 128 + SIGINT(2) = 130；shell `$?` 一看就知道是被中断的。
        sys.stderr.write("\n")
        return 130
    except BrokenPipeError:
        # `talos topic echo ... | head` 之类管道关闭时不要报错
        return 0

if __name__ == "__main__":
    raise SystemExit(main())
