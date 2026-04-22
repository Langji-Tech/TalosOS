#!/usr/bin/env bash
# Build + install TalosOS into an activated Python venv.
#
# 与 install_conda.sh 平行的脚本：针对 `python -m venv` 创建的虚拟环境，
# 把产物（C++ 运行时 + pybind11 扩展 + Python 包 + talos CLI）全部装进
# `$VIRTUAL_ENV`，deactivate 就消失。
#
# venv 和 conda env 的关键差异：
#   * venv 没有 conda 的 toolchain 集成，cmake / ninja / pybind11 都通过
#     `pip install` 拉（wheel 现代、够用）
#   * venv 不能切换 Python 版本 —— 创建时是 python3.X，用到底
#   * Rust / cargo 仍然是系统级依赖（没有 pip 可以装的 cargo），
#     脚本会检测；没有就调用 rustup 装
#
# Usage:
#   python3 -m venv ~/venvs/talos
#   source ~/venvs/talos/bin/activate
#   scripts/install_venv.sh              # rebuild + install into $VIRTUAL_ENV
#   scripts/install_venv.sh --clean      # wipe build dir first
#   JOBS=8 scripts/install_venv.sh
#
# Env overrides:
#   BUILD_DIR       build directory (default: build-venv-<env_name>)
#   BUILD_TYPE      Release | RelWithDebInfo | Debug (default: Release)
#   JOBS            parallel jobs (default: nproc)
#   SKIP_DEPS       1 = don't try to `pip install` missing build tools
#   EXTRA_CMAKE     extra flags appended to cmake configure
#   AUTO_INSTALL_RUST=1   缺 cargo 时自动装 rustup（不问）

set -euo pipefail

# ---- Pretty ---------------------------------------------------------------

if [ -t 1 ]; then
  C_OK=$'\033[1;32m'; C_WARN=$'\033[1;33m'; C_ERR=$'\033[1;31m'
  C_HI=$'\033[1;36m';  C_DIM=$'\033[2m';    C_OFF=$'\033[0m'
else
  C_OK=""; C_WARN=""; C_ERR=""; C_HI=""; C_DIM=""; C_OFF=""
fi

say()  { printf "%s[talosos-venv]%s %s\n"   "$C_HI"   "$C_OFF" "$*"; }
ok()   { printf "%s[talosos-venv]%s %s\n"   "$C_OK"   "$C_OFF" "$*"; }
warn() { printf "%s[talosos-venv]%s %s\n"   "$C_WARN" "$C_OFF" "$*"; }
die()  { printf "%s[talosos-venv]%s %s\n" >&2 "$C_ERR" "$C_OFF" "$*"; exit 1; }

# ---- 1. venv 校验 --------------------------------------------------------

[ -n "${VIRTUAL_ENV:-}" ] || die "没有检测到 venv。先 activate：
    python3 -m venv ~/venvs/talos
    source ~/venvs/talos/bin/activate
  再跑本脚本。"

venv_prefix="${VIRTUAL_ENV}"
venv_py="${venv_prefix}/bin/python"
[ -x "$venv_py" ] || die "$venv_py 不可执行 —— 当前 VIRTUAL_ENV 不是有效的 venv？"

# 防呆：别意外装进 /opt/talosos 之类的系统 venv
case "$venv_prefix" in
  /opt/*|/usr/*)
    warn "VIRTUAL_ENV=$venv_prefix 看起来像系统目录，继续可能需要 sudo；
        大多数情况下你想要的是 ~/venvs/<name>。" ;;
esac

env_name="$(basename "$venv_prefix")"
py_ver="$("$venv_py" -c 'import sys; print("{}.{}".format(*sys.version_info[:2]))')"
py_tag="$("$venv_py" -c 'import sys; print("cpython-{}{}".format(*sys.version_info[:2]))')"

say "venv        : $env_name"
say "prefix      : $venv_prefix"
say "python      : $venv_py  (${py_ver}, $py_tag)"

# ---- 2. 源码路径 ---------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
[ -f "$SRC_DIR/CMakeLists.txt" ] || die "$SRC_DIR/CMakeLists.txt not found."
say "source      : $SRC_DIR"

# ---- 3. 解析 flag --------------------------------------------------------

clean_build=0
for arg in "$@"; do
  case "$arg" in
    --clean|-c) clean_build=1 ;;
    -h|--help)
      sed -n '2,35p' "$0"; exit 0 ;;
    *) die "未知 flag: $arg（用 --help 看）" ;;
  esac
done

BUILD_DIR="${BUILD_DIR:-$SRC_DIR/build-venv-$env_name}"
BUILD_TYPE="${BUILD_TYPE:-Release}"
if [ -z "${JOBS:-}" ]; then
  JOBS="$(command -v nproc >/dev/null && nproc || sysctl -n hw.ncpu 2>/dev/null || echo 4)"
fi

# ---- 4. 在 venv 里装构建工具 ----------------------------------------------

ensure_pip_in_venv() {
  # 有 pip 就不管
  if "$venv_py" -c 'import pip' 2>/dev/null; then
    return 0
  fi
  warn "venv 里没有 pip（可能是 uv / poetry 生成的精简 venv）—— 正在 bootstrap"
  # 先试 ensurepip（Python 自带模块）
  if "$venv_py" -m ensurepip --upgrade 2>/dev/null; then
    ok "ensurepip 成功"
  elif command -v curl >/dev/null 2>&1; then
    say "ensurepip 失败；从 bootstrap.pypa.io 拉 get-pip.py"
    local tmp; tmp="$(mktemp)"
    curl -sS --fail --retry 3 \
         https://bootstrap.pypa.io/get-pip.py -o "$tmp"
    "$venv_py" "$tmp"
    rm -f "$tmp"
  else
    die "venv 里没有 pip 且 curl 也不在 PATH 上。
      手动装 pip：
        $venv_py -m ensurepip --upgrade
      或
        curl -sS https://bootstrap.pypa.io/get-pip.py | $venv_py
      装好再重跑本脚本。"
  fi
  # 升级到较新 pip，避免旧版本的各种奇怪 bug
  "$venv_py" -m pip install -q --upgrade pip setuptools wheel || true
  "$venv_py" -c 'import pip' 2>/dev/null \
    || die "bootstrap 完 pip 仍然 import 不了。"
  ok "pip ready: $("$venv_py" -m pip --version)"
}

install_in_venv() {
  say "pip install（venv 里）: $*"
  "$venv_py" -m pip install -q --upgrade "$@"
}

check_and_install_build_tools() {
  ensure_pip_in_venv

  # 在 venv 里需要：cmake、ninja、pybind11、pyyaml
  local missing=()
  "$venv_py" -c 'import pybind11' 2>/dev/null || missing+=(pybind11)
  "$venv_py" -c 'import yaml'     2>/dev/null || missing+=(pyyaml)
  command -v cmake >/dev/null 2>&1 \
    || "$venv_py" -m cmake --version >/dev/null 2>&1 \
    || missing+=(cmake)
  command -v ninja >/dev/null 2>&1 \
    || "$venv_py" -c 'import ninja' >/dev/null 2>&1 \
    || missing+=(ninja)

  if [ ${#missing[@]} -gt 0 ] && [ -z "${SKIP_DEPS:-}" ]; then
    install_in_venv "${missing[@]}"
  elif [ ${#missing[@]} -gt 0 ]; then
    warn "SKIP_DEPS=1 但仍缺: ${missing[*]}（cmake 可能失败）"
  fi

  # Ensure pip-installed cmake/ninja take precedence
  export PATH="$venv_prefix/bin:$PATH"
}

check_and_install_build_tools

# ---- 5. Rust（venv 管不了这个，走系统） ----------------------------------

if ! command -v cargo >/dev/null 2>&1; then
  warn "未检测到 cargo。zenoh-c 必须用 Rust 编。"
  if [ "${AUTO_INSTALL_RUST:-}" = "1" ] || \
     ( [ -t 0 ] && [ -t 1 ] && \
       { read -rp "要现在用 rustup 装吗？[Y/n] " _r; \
         case "${_r:-Y}" in [yY]|[yY][eE][sS]|"") true;; *) false;; esac; } ); then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
      | sh -s -- -y --default-toolchain stable --no-modify-path >/dev/null
    [ -f "$HOME/.cargo/env" ] && source "$HOME/.cargo/env"
    export PATH="$HOME/.cargo/bin:$PATH"
    command -v cargo >/dev/null 2>&1 || die "rustup 装完仍找不到 cargo"
    ok "Rust 装好：$(cargo --version)"
  else
    die "请先装 Rust 工具链再重试：
      curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
      source \$HOME/.cargo/env"
  fi
fi

# ---- 6. Configure --------------------------------------------------------

if [ $clean_build -eq 1 ] && [ -d "$BUILD_DIR" ]; then
  say "清掉 $BUILD_DIR"
  rm -rf "$BUILD_DIR"
fi
mkdir -p "$BUILD_DIR"

# 每次重刷 CMakeCache（保留已编译对象）——  pip 刚安装过 pybind11 / 刚
# bootstrap 过 pip 时，cmake 上一轮的 "not found" 结果必须重新 probe，
# 否则 _talosos_runtime.so 不会被编出来，Python 端 import 不到。
if [ -f "$BUILD_DIR/CMakeCache.txt" ]; then
  say "刷新 CMake cache（让 pybind11 重新 probe）"
  rm -f "$BUILD_DIR/CMakeCache.txt"
  rm -rf "$BUILD_DIR/CMakeFiles/3."*  2>/dev/null || true
fi

# pip-installed cmake 在 $venv/bin；用 ninja 如有；否则默认 generator
cmake_bin="cmake"
ninja_gen=()
if command -v ninja >/dev/null 2>&1; then
  ninja_gen=(-GNinja)
fi

# Python 开发头 / 库住在 base_prefix（venv 不复制它们，uv 的 Python 更特殊）。
# 查出来显式告诉 cmake，否则 find_package(Python3 Development.Module) 找不到
# → pybind11 扩展静默不编。
py_base="$("$venv_py" -c 'import sys; print(sys.base_prefix)')"
py_sysroot="${py_base}"        # 给 cmake 的 Python3_ROOT_DIR
py_site="lib/python${py_ver}/site-packages"

say "python base_prefix: $py_base"
say "expected site_dir : $py_site"

say "configure (generator: $(if [ ${#ninja_gen[@]} -gt 0 ]; then echo Ninja; else echo default; fi), $BUILD_TYPE)"
# RPATH $ORIGIN 让扩展找到同目录的 libtalosos.so；加上 $venv/lib 做二保险
"$cmake_bin" -S "$SRC_DIR" -B "$BUILD_DIR" "${ninja_gen[@]}" \
  -DCMAKE_BUILD_TYPE="$BUILD_TYPE" \
  -DCMAKE_INSTALL_PREFIX="$venv_prefix" \
  -DPython3_EXECUTABLE="$venv_py" \
  -DPython3_ROOT_DIR="$py_sysroot" \
  -DPython3_FIND_VIRTUALENV=ONLY \
  -DTALOSOS_PYTHON_SITE_DIR_REL="$py_site" \
  -DCMAKE_INSTALL_RPATH='$ORIGIN;$ORIGIN/..;'"$venv_prefix/lib" \
  -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
  -DCMAKE_INSTALL_LIBDIR=lib \
  ${EXTRA_CMAKE:-}

# ---- 7. Build + install --------------------------------------------------

say "building (jobs=$JOBS)"
"$cmake_bin" --build "$BUILD_DIR" --parallel "$JOBS"

say "installing into $venv_prefix"
"$cmake_bin" --install "$BUILD_DIR"

# ---- 8. Verify -----------------------------------------------------------

found_ext="$(find "$venv_prefix/lib/python$py_ver/site-packages/talosos" \
               -name "_talosos_runtime*.so" 2>/dev/null | head -1 || true)"
if [ -z "$found_ext" ]; then
  warn "未在 $venv_prefix/lib/python$py_ver/site-packages/talosos 下找到
      _talosos_runtime*.so；看上面 'ninja install' 日志。"
else
  ok "扩展已装：$found_ext"
  if ! echo "$found_ext" | grep -q "$py_tag"; then
    warn "ABI tag 不匹配期望的 $py_tag —— 这台 venv 的 python 版本可能改过？"
  fi
fi

# 干净环境烟雾测试 —— 避免外部 LD_LIBRARY_PATH / PYTHONPATH 掩盖 RPATH 问题
say "烟雾测试：在干净 env 里 import talosos.runtime"
if env -i HOME="$HOME" PATH="$venv_prefix/bin:/usr/bin:/bin" \
      "$venv_py" -c 'from talosos.runtime import Node, init; init(); \
print("node:", Node.create("venv_smoketest").name())'; then
  ok "import OK —— RPATH 解析干净。"
else
  die "烟雾测试失败，看上面 traceback。"
fi

# ---- 9. 总结 --------------------------------------------------------------

cat <<EOF

${C_OK}═══════════════════════════════════════════════════${C_OFF}
${C_OK} TalosOS installed into venv: ${C_HI}${env_name}${C_OFF}
${C_OK}═══════════════════════════════════════════════════${C_OFF}

  prefix        ${venv_prefix}
  python        ${venv_py}  (${py_ver})
  library       ${venv_prefix}/lib/libtalosos.so
  extension     ${found_ext:-<not found>}
  CLI           ${venv_prefix}/bin/talos

用法（每次开 shell）：
  source ${venv_prefix}/bin/activate
  python -c 'from talosos.runtime import Node, init; init(); print(Node.create("hi").name())'
  talos topic list

源码改了要 rebuild：
  scripts/install_venv.sh             # incremental
  scripts/install_venv.sh --clean     # from scratch

从 venv 卸载（保留 venv）：
  rm -rf \$VIRTUAL_ENV/lib/python${py_ver}/site-packages/talosos
  rm -f  \$VIRTUAL_ENV/lib/libtalosos.so* \$VIRTUAL_ENV/lib/libzenohc.so
  rm -f  \$VIRTUAL_ENV/bin/talos \$VIRTUAL_ENV/bin/talosos_tool

EOF
