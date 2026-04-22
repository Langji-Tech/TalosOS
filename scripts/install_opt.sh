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

set -euo pipefail

# ---- Platform detection ---------------------------------------------------

uname_s="$(uname -s)"
case "${uname_s}" in
  Linux)   platform="linux" ;;
  Darwin)  platform="macos" ;;
  MINGW*|MSYS*|CYGWIN*) platform="windows_posix" ;;
  *)       platform="unknown" ;;
esac

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

echo "TalosOS install"
echo "  platform:   ${platform} (${uname_s})"
echo "  repo:       ${REPO_ROOT}"
echo "  prefix:     ${PREFIX}"
echo "  jobs:       ${JOBS}"
echo "  build type: ${BUILD_TYPE}"
echo

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

Done. Next steps:

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
