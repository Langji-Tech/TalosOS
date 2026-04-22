#!/usr/bin/env python3
"""Generate a TalosOS C++ header from a ROS-style .msg file.

Usage:
  talos_msg_gen.py --package <pkg> --input <Foo.msg> --output <Foo.h>
                   [--namespace talos::<pkg>]

The emitted header exposes a struct with the message's field layout and a
TALOS_MESSAGE_FIELDS(...) macro so CDR serialization is automatic.

Supported field grammar:

  # comment
  <type>       <name>              # scalar field
  <type>[<N>]  <name>              # fixed-size array
  <type>[]     <name>              # dynamic sequence
  <type>       <NAME>=<value>      # constant (must use UPPER_CASE)

Supported <type>:
  - Primitives: bool, int8, int16, int32, int64, uint8, uint16, uint32, uint64,
                float32, float64, string, byte, char, time, duration
  - ROS built-ins: Header
  - Cross-package: <pkg>/<Msg>    -> talos::<pkg>::<Msg>
  - Same-package:  <Msg>          -> talos::<pkg>::<Msg>
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from typing import Optional

_PRIMITIVE_MAP = {
    "bool": "bool",
    "int8": "int8_t",
    "int16": "int16_t",
    "int32": "int32_t",
    "int64": "int64_t",
    "uint8": "uint8_t",
    "uint16": "uint16_t",
    "uint32": "uint32_t",
    "uint64": "uint64_t",
    "float32": "float",
    "float64": "double",
    "string": "std::string",
    "byte": "uint8_t",
    "char": "int8_t",
    "time": "::talos::Time",
    "duration": "::talos::Duration",
}

_BUILTIN_MSG_MAP = {
    "Header": "::talos::msgs::Header",
}

_FIELD_RE = re.compile(
    r"""^\s*
        (?P<type>[A-Za-z_][\w/]*)
        (?:\s*\[(?P<size>\d*)\])?
        \s+
        (?P<name>[A-Za-z_]\w*)
        (?:\s*=\s*(?P<const>.+?))?
        \s*(?:\#.*)?$
    """,
    re.VERBOSE,
)

_IDENT_RE = re.compile(r"^[A-Za-z_]\w*$")


@dataclass
class Field:
    cpp_type: str
    name: str
    is_array: bool = False
    array_size: Optional[int] = None  # None => dynamic


@dataclass
class Constant:
    cpp_type: str
    name: str
    value: str


def _resolve_type(ros_type: str, pkg: str) -> str:
    """Map a ROS-msg type name to its fully qualified C++ type."""
    if ros_type in _PRIMITIVE_MAP:
        return _PRIMITIVE_MAP[ros_type]
    if ros_type in _BUILTIN_MSG_MAP:
        return _BUILTIN_MSG_MAP[ros_type]
    if "/" in ros_type:
        parts = ros_type.split("/")
        if len(parts) != 2 or not all(_IDENT_RE.match(p) for p in parts):
            raise ValueError(f"invalid cross-package type: {ros_type!r}")
        return f"::talos::{parts[0]}::{parts[1]}"
    if _IDENT_RE.match(ros_type):
        return f"::talos::{pkg}::{ros_type}"
    raise ValueError(f"unrecognized type: {ros_type!r}")


def _format_constant(cpp_type: str, raw_value: str) -> str:
    raw = raw_value.strip()
    if cpp_type == "bool":
        lowered = raw.lower()
        if lowered in ("true", "1"):
            return "true"
        if lowered in ("false", "0"):
            return "false"
        raise ValueError(f"bad bool constant: {raw!r}")
    if cpp_type == "std::string":
        if not (raw.startswith('"') and raw.endswith('"')) and not (
            raw.startswith("'") and raw.endswith("'")
        ):
            # ROS msg constants for strings are just the literal text.
            raw = raw.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{raw}"'
        return raw
    if cpp_type.startswith("float") or cpp_type == "double":
        if "." not in raw and "e" not in raw.lower():
            raw = raw + ".0"
        return raw + ("f" if cpp_type == "float" else "")
    # integer types
    return raw


def parse_msg(text: str, pkg: str) -> tuple[list[Field], list[Constant]]:
    fields: list[Field] = []
    constants: list[Constant] = []

    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        m = _FIELD_RE.match(line)
        if not m:
            raise ValueError(f"line {lineno}: cannot parse: {line.rstrip()!r}")

        ros_type = m.group("type")
        raw_size = m.group("size")
        name = m.group("name")
        const_val = m.group("const")

        cpp_scalar = _resolve_type(ros_type, pkg)

        if const_val is not None:
            if raw_size is not None:
                raise ValueError(
                    f"line {lineno}: array constants are not supported"
                )
            if not name.isupper() and "_" not in name:
                # ROS convention is UPPER_CASE; we're permissive but warn.
                pass
            constants.append(
                Constant(cpp_type=cpp_scalar, name=name,
                         value=_format_constant(cpp_scalar, const_val))
            )
            continue

        if raw_size is None:
            fields.append(Field(cpp_type=cpp_scalar, name=name))
        elif raw_size == "":
            fields.append(
                Field(cpp_type=f"std::vector<{cpp_scalar}>", name=name,
                      is_array=True, array_size=None)
            )
        else:
            n = int(raw_size)
            fields.append(
                Field(cpp_type=f"std::array<{cpp_scalar}, {n}>",
                      name=name, is_array=True, array_size=n)
            )

    return fields, constants


def _format_guard(pkg: str, name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9]", "_", f"{pkg}_{name}").upper()
    return f"TALOSOS_GEN_{safe}_H_"


def _zero_literal(cpp_type: str) -> Optional[str]:
    if cpp_type == "bool":
        return "false"
    if cpp_type in ("float",):
        return "0.f"
    if cpp_type == "double":
        return "0.0"
    if cpp_type.startswith("int") or cpp_type.startswith("uint") or cpp_type.endswith(
        "_t"
    ):
        return "0"
    return None


def emit_header(pkg: str, msg_name: str, fields: list[Field],
                constants: list[Constant]) -> str:
    guard = _format_guard(pkg, msg_name)
    lines: list[str] = []
    add = lines.append

    add(f"// Auto-generated by talos_msg_gen.py — DO NOT EDIT.")
    add(f"// Source: {pkg}/msg/{msg_name}.msg")
    add(f"#ifndef {guard}")
    add(f"#define {guard}")
    add("")
    add("#include <array>")
    add("#include <cstdint>")
    add("#include <string>")
    add("#include <tuple>")
    add("#include <vector>")
    add("")
    add('#include "talosos/messages.h"')
    add('#include "talosos/serialization.h"')
    add("")
    add(f"namespace talos::{pkg} {{")
    add("")
    add(f"struct {msg_name} {{")

    for c in constants:
        add(f"  static constexpr {c.cpp_type} {c.name} = {c.value};")
    if constants and fields:
        add("")

    for f in fields:
        init = _zero_literal(f.cpp_type)
        if init is not None:
            add(f"  {f.cpp_type} {f.name} = {init};")
        elif f.cpp_type.startswith("std::array<"):
            add(f"  {f.cpp_type} {f.name}{{}};")
        else:
            add(f"  {f.cpp_type} {f.name};")

    if fields:
        add("")
        names = ", ".join(f.name for f in fields)
        add(f"  TALOS_MESSAGE_FIELDS({names})")
    else:
        add("")
        add("  // Empty message: emit a single padding byte for CDR compliance.")
        add("  uint8_t _structure_needs_at_least_one_member = 0;")
        add("  TALOS_MESSAGE_FIELDS(_structure_needs_at_least_one_member)")

    add("};")
    add("")
    add(f"}}  // namespace talos::{pkg}")
    add("")
    add(f"#endif  // {guard}")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True,
                        help="Logical package name used for talos::<pkg> namespace.")
    parser.add_argument("--input", required=True,
                        help="Path to the .msg source file.")
    parser.add_argument("--output", required=True,
                        help="Path to the generated C++ header.")
    args = parser.parse_args(argv)

    msg_name = os.path.splitext(os.path.basename(args.input))[0]
    if not _IDENT_RE.match(msg_name):
        print(f"error: invalid message filename: {args.input}", file=sys.stderr)
        return 2

    with open(args.input, "r", encoding="utf-8") as f:
        text = f.read()

    try:
        fields, constants = parse_msg(text, args.package)
    except ValueError as e:
        print(f"error: {args.input}: {e}", file=sys.stderr)
        return 2

    header = emit_header(args.package, msg_name, fields, constants)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(header)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
