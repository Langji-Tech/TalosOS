#!/usr/bin/env bash
# Build + install TalosOS under a chosen prefix.
# Works on Linux, macOS, and WSL2. Windows users should use install.ps1.
#
# Usage:
#   scripts/install_opt.sh                 # prefix = /opt/talosos (Linux) or
#                                          #          /usr/local/talosos (macOS)
#   scripts/install_opt.sh /opt/talosos
#   scripts/install_opt.sh ~/talosos       # local, no sudo
#   PREFIX=~/t JOBS=8 scripts/install_opt.sh
#   SKIP_DEPS_CHECK=1 scripts/install_opt.sh   # 跳过前置依赖检查

set -euo pipefail

# ---- Pretty printing ------------------------------------------------------

if [ -t 1 ]; then
  C_OK=$'\033[1;32m'; C_WARN=$'\033[1;33m'; C_ERR=$'\033[1;31m'
  C_HI=$'\033[1;36m';  C_DIM=$'\033[2m';    C_OFF=$'\033[0m'
else
  C_OK=""; C_WARN=""; C_ERR=""; C_HI=""; C_DIM=""; C_OFF=""
fi

# ---- Platform detection ---------------------------------------------------

uname_s="$(uname -s)"
case "${uname_s}" in
  Linux)   platform="linux" ;;
  Darwin)  platform="macos" ;;
  MINGW*|MSYS*|CYGWIN*) platform="windows_posix" ;;
  *)       platform="unknown" ;;
esac

# Linux 下进一步分辨包管理器
PKG_MGR=""
if [ "${platform}" = "linux" ]; then
  if command -v apt-get >/dev/null 2>&1; then PKG_MGR="apt"
  elif command -v dnf  >/dev/null 2>&1; then PKG_MGR="dnf"
  elif command -v yum  >/dev/null 2>&1; then PKG_MGR="yum"
  elif command -v pacman >/dev/null 2>&1; then PKG_MGR="pacman"
  fi
elif [ "${platform}" = "macos" ]; then
  PKG_MGR="brew"
fi

# Default prefix differs by platform (macOS doesn't usually have /opt).
if [ -z "${PREFIX:-}" ] && [ $# -eq 0 ]; then
  case "${platform}" in
    macos) PREFIX="/usr/local/talosos" ;;
    *)     PREFIX="/opt/talosos" ;;
  esac
fi
PREFIX="${1:-${PREFIX}}"

# Default parallelism. macOS has no nproc; fall back to sysctl.
if [ -z "${JOBS:-}" ]; then
  if command -v nproc >/dev/null 2>&1; then
    JOBS="$(nproc)"
  elif command -v sysctl >/dev/null 2>&1; then
    JOBS="$(sysctl -n hw.ncpu 2>/dev/null || echo 4)"
  else
    JOBS=4
  fi
fi

BUILD_TYPE="${BUILD_TYPE:-Release}"
BUILD_DIR="${BUILD_DIR:-build}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

echo "${C_HI}TalosOS install${C_OFF}"
echo "  platform:   ${platform} (${uname_s}${PKG_MGR:+, $PKG_MGR})"
echo "  repo:       ${REPO_ROOT}"
echo "  prefix:     ${PREFIX}"
echo "  jobs:       ${JOBS}"
echo "  build type: ${BUILD_TYPE}"
echo

# ---- Prerequisite checks + auto install ----------------------------------
#
# 检查硬依赖；缺了会提示是否自动安装：apt/dnf/brew/pacman + pip + rustup。
#
# 控制环境变量：
#   AUTO_INSTALL_DEPS=1     缺依赖时直接装，不交互（CI 用）
#   AUTO_INSTALL_DEPS=0     缺依赖时只打印命令然后退出，不装
#   （不设）                终端下询问；非终端时等同 AUTO_INSTALL_DEPS=0
#   SKIP_DEPS_CHECK=1       完全跳过检查

check_missing() {
  MISSING_BINS=(); MISSING_PIP=(); MISSING_HEADERS=(); MISSING_RUST=0

  for bin in cmake python3 pkg-config; do
    command -v "$bin" >/dev/null 2>&1 || MISSING_BINS+=("$bin")
  done
  if ! command -v g++ >/dev/null 2>&1 \
       && ! command -v c++ >/dev/null 2>&1 \
       && ! command -v clang++ >/dev/null 2>&1; then
    MISSING_BINS+=("cxx-compiler")
  fi
  command -v cargo >/dev/null 2>&1 || MISSING_RUST=1

  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import pybind11' 2>/dev/null || MISSING_PIP+=("pybind11")
    python3 -c 'import yaml'     2>/dev/null || MISSING_PIP+=("pyyaml")
  fi

  if [ ! -d /usr/include/eigen3 ] && [ ! -d /usr/local/include/eigen3 ] \
     && [ ! -d /opt/homebrew/include/eigen3 ]; then
    MISSING_HEADERS+=("eigen3")
  fi
}

# 返回 0 如果什么都不缺
deps_ok() {
  [ ${#MISSING_BINS[@]} -eq 0 ] && [ ${#MISSING_PIP[@]} -eq 0 ] \
    && [ ${#MISSING_HEADERS[@]} -eq 0 ] && [ $MISSING_RUST -eq 0 ]
}

report_missing() {
  echo "${C_ERR}缺少以下依赖：${C_OFF}"
  [ ${#MISSING_BINS[@]}    -gt 0 ] && echo "  工具:       ${MISSING_BINS[*]}"
  [ ${#MISSING_HEADERS[@]} -gt 0 ] && echo "  头文件:     ${MISSING_HEADERS[*]}"
  [ ${#MISSING_PIP[@]}     -gt 0 ] && echo "  Python:     ${MISSING_PIP[*]}"
  [ $MISSING_RUST -eq 1 ]           && echo "  Rust:       rustup + cargo"
  echo
}

# 每种 PM 一条"把所有东西都装上"的命令（apt 对已装包幂等，无浪费）
auto_install_sys() {
  case "$PKG_MGR" in
    apt)
      echo "${C_HI}→${C_OFF} sudo apt install ..."
      sudo apt-get update
      sudo apt-get install -y build-essential cmake pkg-config \
           libeigen3-dev python3 python3-pip python3-yaml
      ;;
    dnf|yum)
      echo "${C_HI}→${C_OFF} sudo ${PKG_MGR} install ..."
      sudo "$PKG_MGR" install -y gcc-c++ cmake pkgconfig \
           eigen3-devel python3-pip python3-pyyaml
      ;;
    pacman)
      echo "${C_HI}→${C_OFF} sudo pacman -S ..."
      sudo pacman -S --needed --noconfirm \
           gcc cmake pkgconf eigen python python-pip python-yaml
      ;;
    brew)
      echo "${C_HI}→${C_OFF} brew install ..."
      brew install cmake eigen pkg-config python
      ;;
    *)
      echo "${C_ERR}未识别的包管理器，无法自动安装系统依赖。${C_OFF}" >&2
      return 1
      ;;
  esac
}

auto_install_pip() {
  [ ${#MISSING_PIP[@]} -eq 0 ] && return 0
  echo "${C_HI}→${C_OFF} pip install ${MISSING_PIP[*]}"
  # 旧 pip 不认 --break-system-packages → 先不加，失败再加
  python3 -m pip install --user "${MISSING_PIP[@]}" \
    || python3 -m pip install --user --break-system-packages "${MISSING_PIP[@]}"
}

auto_install_rust() {
  [ $MISSING_RUST -eq 0 ] && return 0
  echo "${C_HI}→${C_OFF} installing Rust via rustup (stable)"
  # -y 非交互、--default-toolchain stable 装稳定版
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --default-toolchain stable --no-modify-path >/dev/null
  # 让当前 shell 也能看到 cargo
  if [ -f "$HOME/.cargo/env" ]; then
    # shellcheck disable=SC1091
    source "$HOME/.cargo/env"
  fi
  export PATH="$HOME/.cargo/bin:$PATH"
}

print_manual_hint() {
  case "$PKG_MGR" in
    apt)
      echo "${C_HI}在 Ubuntu / Debian 手动装：${C_OFF}"
      echo "  sudo apt update"
      echo "  sudo apt install -y build-essential cmake pkg-config libeigen3-dev python3 python3-pip python3-yaml"
      echo "  python3 -m pip install --user pybind11 pyyaml \\"
      echo "    || python3 -m pip install --user --break-system-packages pybind11 pyyaml"
      echo "  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
      echo "  source \"\$HOME/.cargo/env\""
      ;;
    dnf|yum)
      echo "${C_HI}在 Fedora / RHEL 手动装：${C_OFF}"
      echo "  sudo ${PKG_MGR} install -y gcc-c++ cmake pkgconfig eigen3-devel python3-pip python3-pyyaml"
      echo "  python3 -m pip install --user pybind11 pyyaml"
      echo "  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
      ;;
    brew)
      echo "${C_HI}在 macOS 手动装：${C_OFF}"
      echo "  brew install cmake eigen pkg-config python rust"
      echo "  python3 -m pip install --user pybind11 pyyaml"
      ;;
    pacman)
      echo "${C_HI}在 Arch 手动装：${C_OFF}"
      echo "  sudo pacman -S --needed gcc cmake pkgconf eigen python python-pip python-yaml rust"
      echo "  python3 -m pip install --user pybind11"
      ;;
    *)
      echo "${C_WARN}未识别包管理器${C_OFF}。手动装：cmake / Rust(cargo) / Eigen3 /"
      echo "  pkg-config / python3 + pip，Python 包 pybind11、pyyaml。"
      ;;
  esac
  echo
  echo "${C_DIM}或者：${C_OFF} AUTO_INSTALL_DEPS=1 ./scripts/install_opt.sh  —— 自动装"
  echo "${C_DIM}或者：${C_OFF} SKIP_DEPS_CHECK=1   ./scripts/install_opt.sh  —— 跳过检查"
}

check_and_maybe_install() {
  check_missing
  if deps_ok; then return 0; fi

  report_missing

  local auto="${AUTO_INSTALL_DEPS:-}"
  if [ -z "$auto" ]; then
    if [ -t 0 ] && [ -t 1 ]; then
      local reply=""
      printf "要自动安装缺失依赖吗？[Y/n] "
      read -r reply || true
      case "${reply:-Y}" in
        [yY]|[yY][eE][sS]|"") auto=1 ;;
        *) auto=0 ;;
      esac
    else
      echo "${C_DIM}(非交互环境；默认不自动安装)${C_OFF}"
      auto=0
    fi
  fi

  if [ "$auto" != "1" ]; then
    print_manual_hint
    exit 2
  fi

  # 执行自动安装
  auto_install_sys || { print_manual_hint; exit 2; }
  auto_install_pip || { print_manual_hint; exit 2; }
  auto_install_rust || { print_manual_hint; exit 2; }

  # 再查一次；这次缺就真的放弃
  echo
  echo "${C_HI}→${C_OFF} 再次验证依赖..."
  check_missing
  if deps_ok; then
    echo "${C_OK}所有依赖就绪。${C_OFF}"
    return 0
  fi
  echo "${C_ERR}自动安装后仍有缺失项，请手动补齐：${C_OFF}"
  report_missing
  print_manual_hint
  exit 2
}

if [ -z "${SKIP_DEPS_CHECK:-}" ]; then
  echo "[0/3] checking prerequisites…"
  check_and_maybe_install
  echo "      OK"
  echo
fi

# ---- Sudo escalation decision --------------------------------------------

SUDO=""
prefix_dir="$(dirname -- "${PREFIX}")"
# Ownership of the prefix parent decides whether we need sudo.
if [ ! -w "${prefix_dir}" ] && [ ! -w "${PREFIX:-/nonexistent}" ]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
    echo "note: ${PREFIX} is not writable by you; will sudo for the install step."
  else
    echo "error: ${PREFIX} is not writable and sudo is unavailable." >&2
    exit 1
  fi
fi

# ---- Build & install ------------------------------------------------------

echo "[1/3] configuring…"
cmake -S "${REPO_ROOT}" -B "${BUILD_DIR}" \
  -DCMAKE_BUILD_TYPE="${BUILD_TYPE}" \
  -DCMAKE_INSTALL_PREFIX="${PREFIX}"

echo "[2/3] building (jobs=${JOBS})…"
cmake --build "${BUILD_DIR}" -j "${JOBS}"

echo "[3/3] installing to ${PREFIX}…"
${SUDO} cmake --install "${BUILD_DIR}"

cat <<EOF

${C_OK}Done.${C_OFF} Next steps:

  source ${PREFIX}/setup.bash     # bash
  source ${PREFIX}/setup.zsh      # zsh

Then:
  talos --version
  talos pkg create my_pkg --with-node

For macOS: if you hit 'dyld: library not found libzenohc.dylib',
you may need to run once:
  export DYLD_LIBRARY_PATH="${PREFIX}/lib:\${DYLD_LIBRARY_PATH:-}"
(libtalosos.dylib embeds @loader_path but SIP-strict binaries still need
this on some macOS versions.)
EOF
