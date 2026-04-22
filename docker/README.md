# Docker build environments

Use these to produce `.deb` packages that match a specific Ubuntu
release without polluting your host system.

## Ubuntu 20.04 (focal)

```bash
# build the image once
docker build -f docker/ubuntu-2004-deb.Dockerfile -t talosos-deb-2004 .

# produce a .deb into ./build-deb/
docker run --rm -v "$PWD:/src" -w /src talosos-deb-2004 \
    scripts/make_deb.sh
```

Output: `build-deb/talosos_1.0.0-focal_amd64.deb`

## Ubuntu 22.04 (jammy)

Just run `scripts/make_deb.sh` on a 22.04 host or VM — no Dockerfile
needed since jammy has CMake 3.22, GCC 11, Python 3.10 by default.

## Ubuntu 24.04 (noble)

Same as jammy — native build via `scripts/make_deb.sh`.

## Cross-release matrix

| Build host | Produces .deb that installs on |
| --- | --- |
| Ubuntu 20.04 (focal)  | focal + cross-compatible with newer **if** pure Python 3.8 runtime — but pybind11 ABI tag is `cpython-38`, so jammy (3.10) won't load `_talosos_runtime` |
| Ubuntu 22.04 (jammy)  | jammy only (cpython-310) |
| Ubuntu 24.04 (noble)  | noble only (cpython-312) |

**Bottom line**: one `.deb` per target Ubuntu release. Ship all three if
you want broad coverage.
