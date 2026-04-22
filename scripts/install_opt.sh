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

# ---- Prerequisite checks --------------------------------------------------
#
# 提前一次性检查所有硬依赖；少哪个就立即用目标平台的命令告诉用户怎么装。
# 绕过：`SKIP_DEPS_CHECK=1 scripts/install_opt.sh`

check_prereqs() {
  local missing_bins=()
  local missing_pip=()
  local missing_headers=()

  # 二进制工具
  for bin in cmake cargo python3 pkg-config; do
    command -v "$bin" >/dev/null 2>&1 || missing_bins+=("$bin")
  done
  # C++ 编译器 —— 至少有一个
  if ! command -v g++ >/dev/null 2>&1 && ! command -v c++ >/dev/null 2>&1 \
       && ! command -v clang++ >/dev/null 2>&1; then
    missing_bins+=("g++ or clang++")
  fi

  # Python 模块
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import pybind11' 2>/dev/null || missing_pip+=("pybind11")
    python3 -c 'import yaml'     2>/dev/null || missing_pip+=("pyyaml")
  fi

  # Eigen3 头
  if [ ! -d /usr/include/eigen3 ] && [ ! -d /usr/local/include/eigen3 ] \
     && [ ! -d /opt/homebrew/include/eigen3 ]; then
    missing_headers+=("eigen3")
  fi

  # Rust 版本（>=1.70 比较安全）
  if command -v cargo >/dev/null 2>&1; then
    local rust_ver
    rust_ver="$(cargo --version 2>/dev/null | awk '{print $2}')"
    if [ -n "$rust_ver" ]; then
      local major minor
      major="$(echo "$rust_ver" | cut -d. -f1)"
      minor="$(echo "$rust_ver" | cut -d. -f2)"
      if [ "${major:-0}" -lt 1 ] || { [ "${major:-0}" -eq 1 ] && [ "${minor:-0}" -lt 70 ]; }; then
        echo "${C_WARN}warning:${C_OFF} cargo ${rust_ver} 偏老（zenoh-c 建议 >= 1.70）。"
        echo "  如果 build 时报 rust 版本错，用 rustup 升级：rustup update stable"
        echo
      fi
    fi
  fi

  if [ ${#missing_bins[@]} -eq 0 ] && [ ${#missing_pip[@]} -eq 0 ] \
     && [ ${#missing_headers[@]} -eq 0 ]; then
    return 0
  fi

  echo "${C_ERR}缺少以下依赖：${C_OFF}"
  [ ${#missing_bins[@]}    -gt 0 ] && echo "  工具:       ${missing_bins[*]}"
  [ ${#missing_pip[@]}     -gt 0 ] && echo "  Python:     ${missing_pip[*]}"
  [ ${#missing_headers[@]} -gt 0 ] && echo "  头文件:     ${missing_headers[*]}"
  echo

  case "$PKG_MGR" in
    apt)
      local apt_pkgs="build-essential cmake pkg-config libeigen3-dev"
      apt_pkgs+=" python3 python3-pip python3-yaml"
      echo "${C_HI}在 Ubuntu / Debian 装齐所需依赖：${C_OFF}"
      echo
      echo "  sudo apt update"
      echo "  sudo apt install -y ${apt_pkgs}"
      echo "  # pybind11 通过 pip（apt 的版本经常过旧）"
      echo "  python3 -m pip install --user --break-system-packages pybind11 pyyaml"
      echo
      echo "  # Rust（zenoh-c 编译必需）"
      echo "  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
      echo "  source \"\$HOME/.cargo/env\""
      ;;
    dnf|yum)
      echo "${C_HI}在 Fedora / RHEL 装齐所需依赖：${C_OFF}"
      echo
      echo "  sudo ${PKG_MGR} install -y gcc-c++ cmake pkgconfig eigen3-devel python3-pip python3-pyyaml"
      echo "  python3 -m pip install --user pybind11 pyyaml"
      echo "  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
      echo "  source \"\$HOME/.cargo/env\""
      ;;
    brew)
      echo "${C_HI}在 macOS（Homebrew）装齐所需依赖：${C_OFF}"
      echo
      echo "  brew install cmake eigen pkg-config python rust"
      echo "  python3 -m pip install --user pybind11 pyyaml"
      ;;
    pacman)
      echo "${C_HI}在 Arch 装齐所需依赖：${C_OFF}"
      echo
      echo "  sudo pacman -S --needed gcc cmake pkgconf eigen python python-pip python-yaml rust"
      echo "  python3 -m pip install --user pybind11"
      ;;
    *)
      echo "${C_WARN}未识别包管理器${C_OFF}。请用你系统的方式装：cmake / Rust（cargo）/"
      echo "  Eigen3 / pkg-config / python3 + pip，以及 python 包 pybind11、pyyaml。"
      ;;
  esac
  echo
  echo "${C_DIM}装完再重跑：${C_OFF} ./scripts/install_opt.sh"
  echo "${C_DIM}绕过检查：${C_OFF}   SKIP_DEPS_CHECK=1 ./scripts/install_opt.sh"
  exit 2
}

if [ -z "${SKIP_DEPS_CHECK:-}" ]; then
  echo "[0/3] checking prerequisites…"
  check_prereqs
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
