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
    p.add_argument("--type", dest="msg_type", default=None,
                    help="消息类型名，例如 LaserScan / PoseStamped；省略则尝试"
                         "从 publisher 的 liveliness 广播里自动识别。")
    p.add_argument("--raw", action="store_true",
                    help="跳过解码，打印原始 hex 字节（旧行为）。")
    p.add_argument("--max-list", type=int, default=16,
                    help="列表字段最多打印多少项（默认 16）。")
    _add_network_options(p)
    p.set_defaults(func=_do_echo)


def _do_echo(args) -> int:
    topic = _normalize_topic(args.topic)

    # --raw 走旧路径：talosos_tool topic-echo 直接 hex 输出
    if args.raw:
        tool_args = ["topic-echo", topic]
        if args.count:
            tool_args += ["--count", str(args.count)]
        tool_args += _network_tool_args(args)
        return _run_tool(tool_args)

    # 解码路径：先搞清楚类型
    type_name = args.msg_type or _auto_detect_type(args)
    if not type_name:
        print(f"error: 识别不到 {args.topic} 的消息类型。\n"
              f"  手动：talos topic echo {args.topic} --type <TypeName>\n"
              f"  或者：talos topic echo {args.topic} --raw   "
              f"(打印原始 hex 字节)", file=sys.stderr)
        return 2

    from ..messages import resolve_type, decode  # noqa: WPS433
    try:
        type_cls = resolve_type(type_name)
    except KeyError:
        print(f"error: 未知类型 {type_name!r}。Python 侧未注册。\n"
              f"  用 --raw 看 hex 字节，或在 talosos.messages.REGISTRY 注册。",
              file=sys.stderr)
        return 2

    header = _as_topic_name(topic)
    print(f"# topic: {header}")
    print(f"# type:  {type_name}")

    # 优先用 runtime 直接订阅（零 pipe），不行就退回 subprocess iter_samples
    if _try_runtime_echo_available():
        return _echo_via_runtime(topic, type_cls, args)
    return _echo_via_subprocess(topic, type_cls, args)


def _auto_detect_type(args) -> Optional[str]:
    """查 liveliness 列表里这个话题的广播类型，找不到返回 None。"""
    target = _as_topic_name(_normalize_topic(args.topic))
    try:
        entries = _collect_list(args, "topic")
    except Exception:
        return None
    for key, tname, _nodes in entries:
        if key == target and tname:
            return tname
    return None


def _try_runtime_echo_available() -> bool:
    try:
        from ..runtime import Node, init, ok  # noqa: F401
        return True
    except Exception:
        return False


def _echo_via_runtime(topic: str, type_cls, args) -> int:
    import threading
    import time as _time
    from ..runtime import Node, init, ok
    init()
    node = Node.create("talos_echo")
    state = {"n": 0}
    done = threading.Event()
    limit = args.count or 0

    def on_msg(msg):
        print("---")
        print(_format_msg(msg, max_list=args.max_list))
        state["n"] += 1
        if limit and state["n"] >= limit:
            done.set()

    _sub = node.subscribe(topic, type_cls, on_msg)
    try:
        while ok() and not done.is_set():
            _time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    return 0


def _echo_via_subprocess(topic: str, type_cls, args) -> int:
    from ..echo_stream import iter_samples
    from ..messages import decode
    limit = args.count or 0
    n = 0
    try:
        for sample in iter_samples(topic, count=limit):
            try:
                msg = decode(type_cls.TYPE_NAME, sample.payload)
            except Exception as ex:
                print(f"# decode error at sample #{sample.seq}: {ex}",
                      file=sys.stderr)
                continue
            print("---")
            print(_format_msg(msg, max_list=args.max_list))
            n += 1
            if limit and n >= limit:
                break
    except KeyboardInterrupt:
        pass
    return 0


# ---- 结构化打印（rostopic echo 风 YAML）-----------------------------------

def _format_msg(msg, *, indent: int = 0, max_list: int = 16) -> str:
    """Dataclass 消息 → YAML-ish 多行字符串。"""
    import dataclasses as _dc

    sp = "  " * indent
    if msg is None:
        return "null"
    if isinstance(msg, bool):
        return "true" if msg else "false"
    if isinstance(msg, (int, float)):
        return _format_scalar(msg)
    if isinstance(msg, str):
        return _format_string(msg)
    if isinstance(msg, (bytes, bytearray)):
        return f"<{len(msg)} bytes>"

    if _dc.is_dataclass(msg):
        lines: List[str] = []
        for f in _dc.fields(msg):
            # 跳过 ClassVar / TYPE_NAME 等
            if f.name == "TYPE_NAME":
                continue
            val = getattr(msg, f.name)
            if _dc.is_dataclass(val):
                lines.append(f"{sp}{f.name}:")
                lines.append(_format_msg(val, indent=indent + 1,
                                           max_list=max_list))
            elif isinstance(val, list):
                lines.append(
                    f"{sp}{f.name}: "
                    + _format_list(val, indent=indent, max_list=max_list))
            elif isinstance(val, (bytes, bytearray)):
                lines.append(f"{sp}{f.name}: <{len(val)} bytes>")
            elif isinstance(val, str):
                lines.append(f"{sp}{f.name}: {_format_string(val)}")
            elif isinstance(val, bool):
                lines.append(f"{sp}{f.name}: {'true' if val else 'false'}")
            elif isinstance(val, (int, float)):
                lines.append(f"{sp}{f.name}: {_format_scalar(val)}")
            elif val is None:
                lines.append(f"{sp}{f.name}: null")
            else:
                lines.append(f"{sp}{f.name}: {val!r}")
        return "\n".join(lines)

    return repr(msg)


def _format_list(lst: list, *, indent: int, max_list: int) -> str:
    import dataclasses as _dc
    if not lst:
        return "[]"
    show = min(len(lst), max_list)
    truncated = len(lst) > show

    # list[dataclass] —— 走 YAML 块形式
    if _dc.is_dataclass(lst[0]):
        sp = "  " * indent
        out = [""]   # 让 "field: " 后跟换行开新块
        for item in lst[:show]:
            nested = _format_msg(item, indent=indent + 1, max_list=max_list)
            # 把块首 "  " 替换成 "- "
            nested_lines = nested.split("\n")
            first_indent = "  " * (indent + 1)
            first = nested_lines[0]
            first_stripped = (first[len(first_indent):]
                                if first.startswith(first_indent) else first)
            out.append(f"{sp}- {first_stripped}")
            out.extend(nested_lines[1:])
        if truncated:
            out.append(f"{sp}# ... ({len(lst) - show} more)")
        return "\n".join(out)

    # list[scalar] —— 单行 / 截断
    body = ", ".join(_format_scalar(x) for x in lst[:show])
    if truncated:
        return f"[{body}, ... ({len(lst)} total)]"
    return f"[{body}]"


def _format_scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        # 小于 1e-3 或大于 1e6 用科学计数，否则定点 6 位
        if v == 0.0:
            return "0.0"
        import math as _m
        mag = abs(v)
        if mag < 1e-3 or mag >= 1e7:
            return f"{v:.6g}"
        return f"{v:.6f}"
    return str(v)


def _format_string(s: str) -> str:
    """YAML-ish 字符串：多行 / 过长的截断，普通情况加双引号。"""
    if "\n" in s:
        head = s.split("\n", 1)[0][:60]
        return f'"{head}..." ({len(s)} chars, multi-line)'
    if len(s) > 120:
        return f'"{s[:60]}...{s[-20:]}" ({len(s)} chars)'
    # 简单转义
    esc = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{esc}"'

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
    p.add_argument("--type", dest="msg_type", default=None,
                    help="消息类型名，例如 String / PoseStamped / LaserScan。"
                         "与 --yaml 或 --template 搭配使用。")
    payload = p.add_mutually_exclusive_group()
    payload.add_argument("--yaml",
                          help="消息体（YAML dict），按 --type 的 schema 解析。"
                               "示例：--type String --yaml \"data: hello\"")
    payload.add_argument("--hex",  help="原始 hex 字节（legacy）")
    payload.add_argument("--utf8", help="原始 UTF-8 字符串（legacy）")
    p.add_argument("--template", action="store_true",
                    help="只打印 --type 对应的 YAML 空模板，不发布")
    p.add_argument("--count", type=int, default=1,
                    help="发送次数（默认 1；0 = 无限）")
    p.add_argument("--rate", type=float, default=1.0,
                    help="频率 Hz，count != 1 时生效（默认 1）")
    _add_network_options(p)
    p.set_defaults(func=_do_pub)


def _do_pub(args) -> int:
    topic = _normalize_topic(args.topic)

    # ---- 1. --template 模式 ----
    if args.template:
        if not args.msg_type:
            print("error: --template 需要 --type <TypeName>", file=sys.stderr)
            return 2
        from ..messages import resolve_type
        try:
            type_cls = resolve_type(args.msg_type)
        except KeyError as ex:
            print(f"error: {ex}", file=sys.stderr)
            return 2
        print(f"# {args.msg_type} —— 把下面作为 --yaml 的输入")
        print(_yaml_template(type_cls))
        return 0

    # ---- 2. --yaml 模式（推荐的新路径）----
    if args.yaml is not None:
        if not args.msg_type:
            print("error: --yaml 需要 --type <TypeName>\n"
                  "  查模板：talos topic pub <topic> --type <TypeName> --template",
                  file=sys.stderr)
            return 2
        try:
            import yaml as _yaml
        except ImportError:
            print("error: 需要 pyyaml。pip install pyyaml", file=sys.stderr)
            return 2
        from ..messages import resolve_type
        try:
            type_cls = resolve_type(args.msg_type)
        except KeyError as ex:
            print(f"error: {ex}", file=sys.stderr)
            return 2
        try:
            data = _yaml.safe_load(args.yaml)
        except Exception as ex:
            print(f"error: YAML 解析失败: {ex}", file=sys.stderr); return 2
        if data is None:
            data = {}
        try:
            msg = _hydrate(type_cls, data, path=args.msg_type)
        except Exception as ex:
            print(f"error: 构造 {args.msg_type}: {ex}", file=sys.stderr); return 2
        return _publish_msg(topic, msg, args)

    # ---- 3. legacy --hex / --utf8 直通 talosos_tool ----
    if args.hex is not None or args.utf8 is not None:
        tool_args = ["topic-pub", topic]
        if args.hex is not None:
            tool_args += ["--hex", args.hex]
        else:
            tool_args += ["--utf8", args.utf8]
        tool_args += ["--count", str(args.count), "--rate", str(args.rate)]
        tool_args += _network_tool_args(args)
        return _run_tool(tool_args)

    print("error: 请给出消息来源：\n"
          "  --type <T> --yaml \"...\"    (推荐，结构化 YAML)\n"
          "  --type <T> --template       (查 YAML 模板)\n"
          "  --hex / --utf8              (原始字节)",
          file=sys.stderr)
    return 2


# ---- YAML → dataclass hydrator -------------------------------------------

# 某些 list 字段的元素是嵌套 dataclass；Python 侧 dataclass 的类型标注太
# 松散（用的是 list 裸类型），没法从字段里看出来 —— 这里显式登记。
_LIST_ELEMENT_TYPES = {
    "Marker.points":            "Point",
    "Marker.colors":            "ColorRGBA",
    "MarkerArray.markers":      "Marker",
    "TFMessage.transforms":     "TransformStamped",
    "PointCloud2.fields":       "PointField",
    "Path.poses":               "PoseStamped",
}


def _hydrate(cls, data, path: str = "."):
    """从 dict 递归构造 dataclass 实例（漏字段用 default，多字段报错）。"""
    import dataclasses as _dc
    from .. import messages as _msgs

    if not _dc.is_dataclass(cls):
        raise TypeError(f"{path}: {cls.__name__} 不是 dataclass")
    if not isinstance(data, dict):
        raise TypeError(f"{path}: 期望 dict，得到 {type(data).__name__}")

    instance = cls()
    declared = {f.name for f in _dc.fields(cls)}
    for key in data:
        if key not in declared:
            raise ValueError(f"{path}: {cls.__name__} 没有字段 {key!r}")

    for f in _dc.fields(cls):
        if f.name == "TYPE_NAME" or f.name not in data:
            continue
        val = data[f.name]
        default = getattr(instance, f.name)
        sub_path = f"{path}.{f.name}"

        # 嵌套 dataclass
        if _dc.is_dataclass(type(default)):
            setattr(instance, f.name, _hydrate(type(default), val, sub_path))
            continue

        # 列表：要么元素是 dataclass（查 _LIST_ELEMENT_TYPES），要么是标量
        if isinstance(default, list):
            elem_name = _LIST_ELEMENT_TYPES.get(f"{cls.__name__}.{f.name}")
            if elem_name and val and isinstance(val[0], dict):
                elem_cls = (_msgs.REGISTRY.get(elem_name)
                              or getattr(_msgs, elem_name, None))
                if elem_cls is None:
                    raise ValueError(
                        f"{sub_path}: 登记了元素类型 {elem_name} 但找不到类")
                setattr(instance, f.name, [
                    _hydrate(elem_cls, item, f"{sub_path}[{i}]")
                    for i, item in enumerate(val)
                ])
            else:
                setattr(instance, f.name, list(val))
            continue

        # bytes: 接受 hex 字符串 / utf8 字符串 / 整数列表
        if isinstance(default, (bytes, bytearray)):
            if isinstance(val, str):
                try:
                    setattr(instance, f.name, bytes.fromhex(val))
                except ValueError:
                    setattr(instance, f.name, val.encode())
            elif isinstance(val, (list, tuple)):
                setattr(instance, f.name, bytes(val))
            else:
                setattr(instance, f.name, val)
            continue

        # 标量
        setattr(instance, f.name, val)

    return instance


# ---- YAML 模板生成 --------------------------------------------------------

# scalar-wrapper 的 `data` 字段类型是 object（None），按 TYPE_NAME 给个合理默认
_SCALAR_DATA_HINT = {
    "String":  '""',
    "Bool":    "false",
    "Int8":    "0",  "Int16":  "0",  "Int32":  "0",  "Int64":  "0",
    "UInt8":   "0",  "UInt16": "0",  "UInt32": "0",  "UInt64": "0",
    "Float32": "0.0","Float64": "0.0",
}


def _yaml_template(cls, indent: int = 0) -> str:
    import dataclasses as _dc
    sp = "  " * indent
    if not _dc.is_dataclass(cls):
        return "null"
    default = cls()
    type_name = getattr(cls, "TYPE_NAME", cls.__name__)
    lines: List[str] = []
    for f in _dc.fields(cls):
        if f.name == "TYPE_NAME":
            continue
        val = getattr(default, f.name)
        if _dc.is_dataclass(type(val)):
            lines.append(f"{sp}{f.name}:")
            lines.append(_yaml_template(type(val), indent + 1))
            continue
        # scalar-wrapper 的 data 字段
        if f.name == "data" and val is None and type_name in _SCALAR_DATA_HINT:
            lines.append(f"{sp}{f.name}: {_SCALAR_DATA_HINT[type_name]}")
            continue
        if isinstance(val, bool):
            lines.append(f"{sp}{f.name}: false")
        elif isinstance(val, int):
            lines.append(f"{sp}{f.name}: 0")
        elif isinstance(val, float):
            lines.append(f"{sp}{f.name}: 0.0")
        elif isinstance(val, str):
            lines.append(f'{sp}{f.name}: ""')
        elif isinstance(val, (bytes, bytearray)):
            lines.append(f'{sp}{f.name}: ""        # hex or utf8 string')
        elif isinstance(val, list):
            elem_name = _LIST_ELEMENT_TYPES.get(f"{cls.__name__}.{f.name}")
            if elem_name:
                lines.append(f"{sp}{f.name}: []       # list of {elem_name}")
            else:
                lines.append(f"{sp}{f.name}: []")
        else:
            lines.append(f"{sp}{f.name}: null")
    return "\n".join(lines)


# ---- 发布实现 ------------------------------------------------------------

def _publish_msg(topic: str, msg, args) -> int:
    """首选 runtime.Node.advertise → publish；runtime 缺了就走 talosos_tool pipe。"""
    # 尝试 runtime 直发
    try:
        from ..runtime import Node, Rate, init, ok
        _rt_ok = True
    except ImportError:
        _rt_ok = False

    if _rt_ok:
        init()
        node = Node.create("talos_pub")
        pub = node.advertise(topic, type(msg))
        import time as _time
        limit = 0 if args.count == 0 else args.count

        if limit == 1:
            pub.publish(msg)
            _time.sleep(0.1)   # liveliness settle
            return 0

        rate = Rate(args.rate)
        n = 0
        try:
            while ok():
                pub.publish(msg)
                n += 1
                if limit and n >= limit:
                    break
                rate.sleep()
        except KeyboardInterrupt:
            pass
        return 0

    # 回退：编码成 bytes，交给 talosos_tool pub --hex
    try:
        from ..runtime import _CdrWriter, _write_any
    except ImportError:
        print("error: 既没有 _talosos_runtime 扩展，也缺 CDR writer。"
              "重装 TalosOS 并确保 pybind11 编译成功。", file=sys.stderr)
        return 2
    w = _CdrWriter(); _write_any(w, msg)
    payload_hex = w.to_bytes().hex()
    tool_args = ["topic-pub", topic, "--hex", payload_hex,
                 "--count", str(args.count), "--rate", str(args.rate)]
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
