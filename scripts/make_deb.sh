#!/usr/bin/env bash
# Build a TalosOS .deb for the host Ubuntu release.
#
# Usage:
#   scripts/make_deb.sh                        # build + package
#   scripts/make_deb.sh --clean                # wipe build dir first
#   BUILD_DIR=build-deb scripts/make_deb.sh    # override build dir
#
# The produced .deb lands in the build directory, named
#   talosos_<version>-<codename>_<arch>.deb
# e.g. talosos_1.0.0-jammy_amd64.deb
#
# Hard requirements on the build host:
#   - Ubuntu 20.04+
#   - cmake >= 3.16, gcc >= 9, rustc (for bundled zenoh-c)
#   - python3-dev, pybind11, eigen3, libopencv-dev (optional)
#   - dpkg-dev (ships dpkg-shlibdeps, required by CPack DEB generator)
#
# The resulting .deb is tied to the build host's Python minor version
# (embedded ABI tag on the pybind11 extension). Build on the same Ubuntu
# release you plan to install on, or use docker/ubuntu-2004-deb.Dockerfile
# for a reproducible 20.04 build.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

BUILD_DIR="${BUILD_DIR:-build-deb}"
BUILD_TYPE="${BUILD_TYPE:-Release}"
JOBS="${JOBS:-$(nproc 2>/dev/null || echo 4)}"
PREFIX="${PREFIX:-/opt/talosos}"

if [ "${1:-}" = "--clean" ]; then
    echo "[clean] removing ${BUILD_DIR}"
    rm -rf "${BUILD_DIR}"
fi

# Preflight — every tool we need.
missing=()
for c in cmake cargo dpkg dpkg-shlibdeps lsb_release python3; do
    command -v "$c" >/dev/null 2>&1 || missing+=("$c")
done
if [ ${#missing[@]} -gt 0 ]; then
    echo "error: missing required tools: ${missing[*]}" >&2
    echo "  sudo apt install build-essential cmake cargo dpkg-dev lsb-release python3-dev" >&2
    exit 1
fi

codename="$(lsb_release -cs)"
arch="$(dpkg --print-architecture)"
pyver="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "Build host: Ubuntu ${codename} / ${arch} / Python ${pyver}"
echo

echo "[1/3] configuring…"
cmake -S "${REPO_ROOT}" -B "${BUILD_DIR}" \
      -DCMAKE_BUILD_TYPE="${BUILD_TYPE}" \
      -DCMAKE_INSTALL_PREFIX="${PREFIX}"

echo "[2/3] building (jobs=${JOBS})…"
cmake --build "${BUILD_DIR}" -j "${JOBS}"

echo "[3/3] packaging → .deb …"
( cd "${BUILD_DIR}" && cpack -G DEB )

deb=$(ls -1t "${BUILD_DIR}"/talosos_*.deb 2>/dev/null | head -n1)
if [ -z "${deb}" ] || [ ! -f "${deb}" ]; then
    echo "error: no .deb produced under ${BUILD_DIR}/" >&2
    exit 2
fi

echo
echo "Produced: ${deb}"
ls -la "${deb}"
echo
dpkg-deb -I "${deb}" | head -30
echo
echo "Install on the target machine with:"
echo "    sudo apt install ./${deb}"
echo "or"
echo "    sudo dpkg -i ${deb} && sudo apt-get -f install"
