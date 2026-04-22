#!/usr/bin/env bash
# Build + install TalosOS into an activated conda environment.
#
# Unlike install_opt.sh (which installs to /opt/talosos as a system-wide,
# single-Python package), this script rebuilds the pybind11 extension
# against the conda env's Python and drops everything into $CONDA_PREFIX.
# That way:
#   * Each env has its own TalosOS, pinned to its Python ABI.
#   * `conda activate <env>` → `talos` / `import talosos` just work.
#   * `conda deactivate`      → they vanish.
#
# Usage:
#   conda activate myenv
#   scripts/install_conda.sh              # rebuild + install to $CONDA_PREFIX
#   scripts/install_conda.sh --clean      # wipe build dir first
#   JOBS=8 scripts/install_conda.sh
#
# Environment overrides:
#   BUILD_DIR       build directory (default: build-conda-<env_name>)
#   BUILD_TYPE      Release | RelWithDebInfo | Debug (default: Release)
#   JOBS            parallel jobs (default: nproc)
#   SKIP_DEPS=1     don't try to `conda install` cmake/ninja/pybind11
#   EXTRA_CMAKE     extra flags appended to cmake configure

set -euo pipefail

# ---- Pretty printing ------------------------------------------------------

if [ -t 1 ]; then
  C_OK=$'\033[1;32m'; C_WARN=$'\033[1;33m'; C_ERR=$'\033[1;31m'
  C_HI=$'\033[1;36m';  C_DIM=$'\033[2m';    C_OFF=$'\033[0m'
else
  C_OK=""; C_WARN=""; C_ERR=""; C_HI=""; C_DIM=""; C_OFF=""
fi

say()  { printf "%s[talosos-conda]%s %s\n"   "$C_HI"   "$C_OFF" "$*"; }
ok()   { printf "%s[talosos-conda]%s %s\n"   "$C_OK"   "$C_OFF" "$*"; }
warn() { printf "%s[talosos-conda]%s %s\n"   "$C_WARN" "$C_OFF" "$*"; }
die()  { printf "%s[talosos-conda]%s %s\n" >&2 "$C_ERR" "$C_OFF" "$*"; exit 1; }

# ---- 1. Sanity: conda env must be active ---------------------------------

[ -n "${CONDA_PREFIX:-}" ] || die "No conda env active. Run 'conda activate <env>' first."
[ "${CONDA_DEFAULT_ENV:-}" != "base" ] || \
  warn "You are in conda's BASE env. Strongly recommend a dedicated env: 'conda create -n talos python=3.12 && conda activate talos'."

env_name="${CONDA_DEFAULT_ENV:-unknown}"
env_prefix="${CONDA_PREFIX}"
env_py="${env_prefix}/bin/python"
[ -x "$env_py" ] || die "Can't find python at $env_py — is this really a conda env?"

py_ver="$("$env_py" -c 'import sys; print("{}.{}".format(*sys.version_info[:2]))')"
py_tag="$("$env_py" -c 'import sys; print("cpython-{}{}".format(*sys.version_info[:2]))')"

say "conda env   : $env_name"
say "prefix      : $env_prefix"
say "python      : $env_py  (${py_ver}, $py_tag)"

# ---- 2. Locate TalosOS source --------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
[ -f "$SRC_DIR/CMakeLists.txt" ] || die "$SRC_DIR/CMakeLists.txt not found."
say "source      : $SRC_DIR"

# ---- 3. Parse flags ------------------------------------------------------

clean_build=0
for arg in "$@"; do
  case "$arg" in
    --clean|-c) clean_build=1 ;;
    -h|--help)
      sed -n '2,30p' "$0"
      exit 0 ;;
    *) die "Unknown flag: $arg (use --help)" ;;
  esac
done

BUILD_DIR="${BUILD_DIR:-$SRC_DIR/build-conda-$env_name}"
BUILD_TYPE="${BUILD_TYPE:-Release}"
if [ -z "${JOBS:-}" ]; then
  JOBS="$(command -v nproc >/dev/null && nproc || sysctl -n hw.ncpu 2>/dev/null || echo 4)"
fi

# ---- 4. Install build deps inside the env --------------------------------

missing=()
for tool in cmake ninja; do
  command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done
if ! "$env_py" -c 'import pybind11' 2>/dev/null; then
  missing+=("pybind11")
fi

if [ ${#missing[@]} -gt 0 ] && [ -z "${SKIP_DEPS:-}" ]; then
  if ! command -v conda >/dev/null 2>&1; then
    die "conda CLI not on PATH but build tools missing: ${missing[*]}"
  fi
  say "Installing into env: ${missing[*]}"
  conda install -n "$env_name" -c conda-forge -y "${missing[@]}"
elif [ ${#missing[@]} -gt 0 ]; then
  warn "SKIP_DEPS=1 set but tools missing: ${missing[*]} — cmake may fail."
fi

# ---- 5. Configure --------------------------------------------------------

if [ $clean_build -eq 1 ] && [ -d "$BUILD_DIR" ]; then
  say "Wiping $BUILD_DIR"
  rm -rf "$BUILD_DIR"
fi
mkdir -p "$BUILD_DIR"

# Refresh CMakeCache so pybind11 / Python probes pick up anything conda
# just installed this run. Preserves compiled object files.
if [ -f "$BUILD_DIR/CMakeCache.txt" ]; then
  say "Refreshing CMake cache (re-probing pybind11 / Python)"
  rm -f "$BUILD_DIR/CMakeCache.txt"
  rm -rf "$BUILD_DIR/CMakeFiles/3."* 2>/dev/null || true
fi

# Explicit Python layout — query sysconfig to pin Python.h + libpython
# locations, avoiding the Development.Module probe failures we hit on
# conda / uv venvs.
py_base="$("$env_py" -c 'import sys; print(sys.base_prefix)')"
py_site="lib/python${py_ver}/site-packages"
py_inc="$("$env_py" -c 'import sysconfig; print(sysconfig.get_paths()["include"])')"
py_libdir="$("$env_py" -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR") or "")')"
py_ldlib="$("$env_py" -c 'import sysconfig; print(sysconfig.get_config_var("LDLIBRARY") or "")')"
py_instso="$("$env_py" -c 'import sysconfig; print(sysconfig.get_config_var("INSTSONAME") or "")')"
py_lib=""
for cand in "$py_libdir/$py_ldlib" "$py_libdir/$py_instso" \
            "$py_libdir/libpython${py_ver}.so" \
            "$py_libdir/libpython${py_ver}.so.1.0" \
            "$py_base/lib/$py_ldlib" \
            "$py_base/lib/$py_instso"; do
  if [ -n "$cand" ] && [ -f "$cand" ]; then
    py_lib="$cand"; break
  fi
done

say "python base_prefix  : $py_base"
say "python include dir  : $py_inc"
say "python library file : ${py_lib:-<not found; cmake will probe>}"
say "target site_dir     : $py_site"

if [ ! -f "$py_inc/Python.h" ]; then
  cat >&2 <<EOF
${C_ERR}FATAL${C_OFF}: conda env's Python has no dev headers.
  Missing: $py_inc/Python.h

  Likely cause: this env uses \`pkgs/main\`'s Python (Anaconda default
  channel) which in recent versions stopped shipping the Python dev
  headers — so no C/C++ extension can build.

  Fix: replace with conda-forge's Python (which includes headers):

      conda install -n $env_name -c conda-forge python=${py_ver} -y
      ./scripts/install_conda.sh --clean

  Or rebuild the env from scratch against conda-forge:

      conda deactivate
      conda env remove -n $env_name -y
      conda create -n $env_name -c conda-forge python=${py_ver} -y
      conda activate $env_name
      ./scripts/install_conda.sh --clean
EOF
  exit 2
fi

cmake_py_args=(
  -DPython3_EXECUTABLE="$env_py"
  -DPython3_ROOT_DIR="$py_base"
  # FIRST: allow fallback to Python3_ROOT_DIR when venv lacks headers.
  -DPython3_FIND_VIRTUALENV=FIRST
  -DPython3_FIND_STRATEGY=LOCATION
)
[ -d "$py_inc" ]  && cmake_py_args+=(-DPython3_INCLUDE_DIR="$py_inc")
[ -n "$py_lib" ]  && cmake_py_args+=(-DPython3_LIBRARY="$py_lib")

say "Configuring (Ninja, $BUILD_TYPE)"
# RPATH = $ORIGIN gives the extension a relative runpath back to libtalosos.so
# living next to it in <prefix>/lib — so the env is self-contained and doesn't
# need LD_LIBRARY_PATH at runtime.
cmake -S "$SRC_DIR" -B "$BUILD_DIR" -GNinja \
  -DCMAKE_BUILD_TYPE="$BUILD_TYPE" \
  -DCMAKE_INSTALL_PREFIX="$env_prefix" \
  "${cmake_py_args[@]}" \
  -DTALOSOS_PYTHON_SITE_DIR_REL="$py_site" \
  -DCMAKE_INSTALL_RPATH='$ORIGIN;$ORIGIN/..;'"$env_prefix/lib" \
  -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
  -DCMAKE_INSTALL_LIBDIR=lib \
  ${EXTRA_CMAKE:-}

# ---- 6. Build + install --------------------------------------------------

say "Building ($JOBS jobs)"
cmake --build "$BUILD_DIR" --parallel "$JOBS"

say "Installing to $env_prefix"
cmake --install "$BUILD_DIR"

# ---- 7. Verify -----------------------------------------------------------

# Pybind11 extension must match this env's Python ABI tag.
found_ext="$(find "$env_prefix/lib/python$py_ver/site-packages/talosos" \
               -name "_talosos_runtime*.so" 2>/dev/null | head -1 || true)"
if [ -z "$found_ext" ]; then
  warn "No _talosos_runtime*.so found under $env_prefix/lib/python$py_ver/site-packages/talosos"
  warn "Install may have landed in an unexpected path — check 'ninja install' log above."
else
  ok "Installed extension: $found_ext"
  if ! echo "$found_ext" | grep -q "$py_tag"; then
    warn "Extension tag does not match $py_tag — ABI mismatch likely."
  fi
fi

# Import smoke test. Run in a clean env so stray LD_LIBRARY_PATH / PYTHONPATH
# from elsewhere can't mask a real RPATH problem.
say "Smoke-testing 'import talosos.runtime' in a clean environment"
if env -i \
      HOME="$HOME" \
      PATH="$env_prefix/bin:/usr/bin:/bin" \
      "$env_py" -c 'from talosos.runtime import Node, init; init(); \
print("node:", Node.create("conda_smoketest").name)'; then
  ok "Python import works (RPATH resolved cleanly)."
else
  die "Smoke test failed — check the traceback above."
fi

# ---- 8. Summary ----------------------------------------------------------

cat <<EOF

${C_OK}═══════════════════════════════════════════════════${C_OFF}
${C_OK} TalosOS installed into conda env: ${C_HI}${env_name}${C_OFF}
${C_OK}═══════════════════════════════════════════════════${C_OFF}

  prefix        ${env_prefix}
  python        ${env_py}  (${py_ver})
  library       ${env_prefix}/lib/libtalosos.so
  extension     ${found_ext:-<not found>}
  CLI           ${env_prefix}/bin/talos

Use it:
  ${C_DIM}# already active now; next time just:${C_OFF}
  conda activate ${env_name}
  python -c 'from talosos.runtime import Node, init; init(); print(Node.create("hi").name)'
  talos topic list

To rebuild after source changes:
  scripts/install_conda.sh             # incremental
  scripts/install_conda.sh --clean     # from scratch

To wipe TalosOS from this env (keep the env):
  rm -rf \$CONDA_PREFIX/lib/python${py_ver}/site-packages/talosos
  rm -f  \$CONDA_PREFIX/lib/libtalosos.so* \$CONDA_PREFIX/lib/libzenohc.so
  rm -f  \$CONDA_PREFIX/bin/talos \$CONDA_PREFIX/bin/talosos_tool

EOF
