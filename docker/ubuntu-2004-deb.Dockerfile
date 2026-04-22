# Reproducible build env for a Ubuntu 20.04 TalosOS .deb.
#
# Build a 20.04-compatible .deb from any host:
#
#   docker build -f docker/ubuntu-2004-deb.Dockerfile -t talosos-deb-2004 .
#   docker run --rm -v "$PWD:/src" -w /src talosos-deb-2004 \
#       scripts/make_deb.sh
#
# The .deb lands at build-deb/talosos_<ver>-focal_amd64.deb on the host.

FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

# Core toolchain.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        cmake \
        dpkg-dev \
        lsb-release \
        pkg-config \
        git \
    && rm -rf /var/lib/apt/lists/*

# Ubuntu 20.04 ships CMake 3.16 — already sufficient for TalosOS (>= 3.16).
# GCC 9 is default, also sufficient for C++17.

# Rust toolchain (zenoh-c crate build).
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- --default-toolchain stable --profile minimal -y \
    && /root/.cargo/bin/rustc --version
ENV PATH="/root/.cargo/bin:${PATH}"

# Python + dev headers for pybind11 extension.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-dev \
        python3-pip \
        python3-yaml \
        python3-pybind11 \
        libeigen3-dev \
    && rm -rf /var/lib/apt/lists/*

# Optional: OpenCV 4 (ships 4.2 on focal, enough for cv_bridge).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libopencv-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

CMD ["scripts/make_deb.sh"]
