# 安装

**Ubuntu 20.04 / 22.04 / 24.04 官方推荐走 `.deb` 包**（一键 `apt install`）；其它平台 / 需要定制编译选项则从源码构建。

## 最简路径 — 安装 `.deb`（Ubuntu 20.04+）

从我们发布的 `.deb` 直接 apt install：

```bash
# 1. 下载与当前 Ubuntu 代号匹配的 .deb
#    例如：talosos_1.0.0-focal_amd64.deb  (20.04)
#          talosos_1.0.0-jammy_amd64.deb  (22.04)
#          talosos_1.0.0-noble_amd64.deb  (24.04)
wget https://example.com/talosos/releases/talosos_1.0.0-$(lsb_release -cs)_$(dpkg --print-architecture).deb

# 2. 安装（apt 会自动把依赖拉上）
sudo apt install ./talosos_1.0.0-*_amd64.deb

# 3. 激活
source /opt/talosos/setup.bash          # bash
# 或：source /opt/talosos/setup.zsh

# 4. 验证
talos --version                          # → talos 1.0.0
talos pkg create my_pkg --with-node
```

!!! info ".deb 与 Ubuntu 版本绑定"
    pybind11 Python 绑定带 CPython ABI tag（如 `cpython-310`），所以
    **一个 `.deb` 只能装在同 Ubuntu 代号的机器上**。20.04 的 deb 装到
    22.04 上会缺 `_talosos_runtime` 扩展。下载时选你 `lsb_release -cs`
    输出那个代号的版本即可。

安装位置一览：

| 路径 | 内容 |
| --- | --- |
| `/opt/talosos/bin/talos` + `/opt/talosos/bin/talosos_tool` | CLI 可执行 |
| `/opt/talosos/lib/libtalosos.so*` + `libzenohc.so` | C++ 运行时 |
| `/opt/talosos/include/talosos/*` + `zenoh/*` | 头文件 |
| `/opt/talosos/lib/cmake/TalosOS/` | `find_package(TalosOS)` |
| `/opt/talosos/lib/python3/dist-packages/talosos/` | Python 包 + pybind11 扩展 |
| `/opt/talosos/setup.{sh,bash,zsh}` | 激活脚本 |
| `/opt/talosos/share/talosos/` | 补全 + Python 示例 |

卸载：`sudo apt remove talosos`（`purge` 一并清走配置）。

## 自己打 .deb

如果你想给公司内网分发自己打 `.deb`：

```bash
# 在目标 Ubuntu 版本的机器或容器上：
sudo apt install build-essential cmake dpkg-dev lsb-release cargo \
                 python3-dev python3-pybind11 python3-yaml libeigen3-dev \
                 libopencv-dev
git clone <your-mirror>/TalosOS && cd TalosOS
bash scripts/make_deb.sh
# 产出: build-deb/talosos_1.0.0-<codename>_<arch>.deb
```

想要在非目标机器打包（例如在 24.04 机器上给 20.04 打包），用我们提供的 Docker：

```bash
docker build -f docker/ubuntu-2004-deb.Dockerfile -t talosos-deb-2004 .
docker run --rm -v "$PWD:/src" -w /src talosos-deb-2004 scripts/make_deb.sh
# 产出 build-deb/talosos_1.0.0-focal_amd64.deb
```

## 平台支持矩阵

| 平台 | 状态 | 最小系统 |
|---|---|---|
| **Ubuntu 22.04 / 24.04** | :material-check-bold: 一级支持（CI 覆盖）| 自带 CMake 3.22+ / GCC 11+ / Python 3.10+ |
| **Ubuntu 20.04** | :material-check-bold: 可用 | 需 Kitware PPA 升 CMake 到 3.16+ |
| **Ubuntu 18.04** | :material-check: 可用（需升级工具链）| 需 CMake 3.16+、GCC 9+、Python 3.7+ |
| **Debian 11+ / Fedora 36+** | :material-check: 可用 | 自带包通常满足 |
| **macOS 12+ (Intel / Apple Silicon)** | :material-check: 可用 | 需 Xcode CLT + Homebrew |
| **WSL2 (Windows)** | :material-check-bold: 一级支持 | 按 Ubuntu 22.04 流程 |
| **Windows 原生** | :material-alert: 实验性 | 仅 C++ 部分测过；CLI / launch / rqt 推荐用 WSL2 |

## 最小构建依赖

| 组件 | 最低版本 | 原因 |
|---|---|---|
| **CMake** | ≥ 3.16 | 根 `CMakeLists.txt` 与 zenoh-c 共同要求 |
| **C++ 编译器** | GCC ≥ 9 / Clang ≥ 10 / MSVC 2019+ | C++17 |
| **Rust toolchain** | 近两年版本 | 构建 `zenoh-c` crate |
| **Python 3** | ≥ 3.7 | `talos` CLI + 运行时绑定 |
| **pybind11** | ≥ 2.10 | Python 运行时绑定（pip 装）|
| **Eigen3** | 任意 | 头文件依赖 |
| Optional: OpenCV | ≥ 4.0 | cv_bridge + `opencv_demo` |
| Optional: matplotlib / PyQt5 | 近代 | `talos plot / viz / rqt` |
| Optional: pyqtgraph ≥ 0.13 + PyOpenGL | 近代 | rqt 3D 面板 GPU 硬件渲染（点云 / 激光 / 位姿 / Marker）|
| Optional: PyYAML | 近代 | CLI 工作空间解析 |

---

## 从源码构建（所有平台都可用）

下面是**不打 .deb** 直接源码装的路径。生产部署推荐上面的 `.deb`；
开发者想改 TalosOS 自身就走这条。

## Ubuntu 22.04 / 24.04 — 源码

```bash
sudo apt update
sudo apt install -y build-essential cmake libeigen3-dev \
                    python3-pip python3-yaml python3-matplotlib python3-pyqt5 \
                    libopencv-dev cargo
pip install --user --break-system-packages pybind11 pyqtgraph PyOpenGL

git clone <your-mirror>/TalosOS && cd TalosOS
scripts/install_opt.sh                          # 默认 /opt/talosos，会 sudo
source /opt/talosos/setup.bash
talos --version
```

## Ubuntu 20.04

20.04 自带 CMake 3.16，够用；默认 GCC 9 也够 C++17。主要麻烦是 Rust 要自己
装：

```bash
# Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"

# 其它同 22.04
sudo apt install -y build-essential cmake libeigen3-dev \
                    python3-pip python3-yaml python3-matplotlib python3-pyqt5 \
                    libopencv-dev
pip install --user pybind11

scripts/install_opt.sh
source /opt/talosos/setup.bash
```

## Ubuntu 18.04 — 需要升级 3 样工具链 { #ubuntu-1804 }

Bionic 自带 CMake 3.10、GCC 7、Python 3.6，三个都达不到 TalosOS 的最低
要求。以下一次性升级后可用：

```bash
# CMake 3.16+
curl -sSL https://apt.kitware.com/kitware-archive.sh | sudo bash
sudo apt install -y cmake

# GCC 9 (C++17 OK)
sudo add-apt-repository -y ppa:ubuntu-toolchain-r/test
sudo apt install -y g++-9
sudo update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-9 90
sudo update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-9 90

# Python 3.7+（deadsnakes）
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt install -y python3.7 python3.7-venv python3.7-dev python3-pip
# 把 python3 指向 3.7（小心影响系统脚本；用 venv 更安全）
# sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.7 90

# Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"

# 剩余依赖
sudo apt install -y build-essential libeigen3-dev python3-pip libopencv-dev
pip install --user pybind11

# （可选）venv 里跑 talos 以避开 Python 3.6 的 apt 包管理
python3.7 -m venv ~/.talos_venv
source ~/.talos_venv/bin/activate
pip install pyyaml matplotlib pybind11

# 最后正常安装
scripts/install_opt.sh
source /opt/talosos/setup.bash
```

!!! warning "18.04 已结束标准支持"
    Ubuntu 18.04 自 2023 年 4 月起已进入 ESM 阶段，社区不再更新工具链。
    **长期运行推荐升级到 22.04/24.04**。

## macOS (Intel / Apple Silicon) { #macos-intel-apple-silicon }

```bash
# Xcode Command Line Tools
xcode-select --install

# Homebrew 包
brew install cmake eigen python@3.11 rust opencv pyqt@5
# 可选：brew install pyqt              # 只 GUI 需要

# pybind11 + 其它 Python 库
python3 -m pip install --user pybind11 pyyaml matplotlib

git clone <your-mirror>/TalosOS && cd TalosOS
scripts/install_opt.sh                                # 默认 /usr/local/talosos
source /usr/local/talosos/setup.bash                  # bash
# 或 setup.zsh（macOS 默认 zsh）
```

构建链细节：
- TalosOS 的 `INSTALL_RPATH` 在 macOS 自动变成 `@loader_path`，所以 `libtalosos.dylib`
  会在同目录找 `libzenohc.dylib`，**不需要** `DYLD_LIBRARY_PATH`。
- 如果仍遇到 `dyld: library not found`（SIP 严格模式下偶发）：
  ```bash
  export DYLD_LIBRARY_PATH="/usr/local/talosos/lib:$DYLD_LIBRARY_PATH"
  ```

## WSL2 on Windows — 推荐的 Windows 路径

WSL2 + Ubuntu 22.04 等同于 Linux，体验最顺：

```powershell
# 在 PowerShell（管理员）
wsl --install -d Ubuntu-22.04
```

然后在 Ubuntu 终端里照 22.04 流程走即可。GUI（`talos rqt` / matplotlib）
在 WSLg 下也能正常显示窗口。

## Windows 原生 — 实验性

Python CLI 依赖 POSIX shell 来 source setup 脚本，日常使用体验不好；建议
只在需要 C++ 运行时库的嵌入式 / 工业场景用：

```powershell
# 先装：Visual Studio 2019+ C++ build tools、CMake 3.16+、Rust、Python 3.7+
# 然后：
pwsh .\scripts\install.ps1 -Prefix C:\talosos
# 或
pwsh .\scripts\install.ps1 -Prefix $env:USERPROFILE\talosos
```

Windows 原生已知限制：

- Setup 脚本只有 PowerShell 版（没有 bash/zsh）
- `talos launch` 的信号流程（SIGINT→SIGTERM→SIGKILL）在 Windows 上用
  `GenerateConsoleCtrlEvent` 模拟，回收不如 Linux 干净
- 彩色日志在非 Windows Terminal 下要先 `ENABLE_VIRTUAL_TERMINAL_PROCESSING`，
  库里已经自动做
- 补全脚本仅 bash/zsh；pwsh 没有

**因此：** 生产环境请用 Linux 或 WSL2；Windows 原生目前做**实验 / 工业
控制柜 native DLL** 用。

---

## Conda 独立环境 { #conda }

想把 TalosOS 塞进某个 conda env 里、不污染系统 Python？按 env 的 Python
版本二选一。

!!! warning "pybind11 扩展与 Python 版本严格绑定"

    `_talosos_runtime.cpython-3XX-*.so` 的 ABI tag 是硬约束，**3.12 编的
    扩展 3.11 装不上**。这是 `.deb` 不能直接走 conda 的根本原因。

### 方案 A · env 用 Python 3.12（不用重编）

`.deb` / `install_opt.sh` 默认打的是 cpython-312 扩展。env 与之匹配，直接
把 `/opt/talosos` 挂进 conda 激活钩子就能用：

```bash
conda create -n talos python=3.12 -y
conda activate talos

mkdir -p $CONDA_PREFIX/etc/conda/activate.d
mkdir -p $CONDA_PREFIX/etc/conda/deactivate.d

cat > $CONDA_PREFIX/etc/conda/activate.d/talosos.sh <<'EOF'
export TALOSOS_ROOT=/opt/talosos
export _TALOS_OLD_PATH="$PATH"
export _TALOS_OLD_PYTHONPATH="${PYTHONPATH:-}"
export _TALOS_OLD_LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"
export PATH="$TALOSOS_ROOT/bin:$PATH"
export PYTHONPATH="$TALOSOS_ROOT/lib/python3.12/site-packages${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$TALOSOS_ROOT/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
EOF

cat > $CONDA_PREFIX/etc/conda/deactivate.d/talosos.sh <<'EOF'
export PATH="$_TALOS_OLD_PATH"
export PYTHONPATH="$_TALOS_OLD_PYTHONPATH"
export LD_LIBRARY_PATH="$_TALOS_OLD_LD_LIBRARY_PATH"
unset _TALOS_OLD_PATH _TALOS_OLD_PYTHONPATH _TALOS_OLD_LD_LIBRARY_PATH TALOSOS_ROOT
EOF

conda deactivate && conda activate talos
python -c "from talosos.runtime import Node, init; init(); print(Node.create('hi').name())"
```

`LD_LIBRARY_PATH` 必加 —— `/opt/talosos` 安装的扩展没 RPATH，也不在
ldconfig 缓存中。

### 方案 B · env 用其他 Python 版本（重编进 env）

需要 3.10 / 3.11 / 3.13 等其它版本时，必须针对 env 重编一次，产物全部落到
`$CONDA_PREFIX`，env 完全自包含：

```bash
conda activate mypy311              # 任意非 3.12 env
cd /path/to/TalosOS
scripts/install_conda.sh            # 首次：自动 conda install cmake ninja pybind11
scripts/install_conda.sh --clean    # 源码改动后从头重编
```

脚本会：

1. 校验 conda env 已激活、非 base
2. 检测 Python 版本，必要时 `conda install -c conda-forge cmake ninja pybind11`
3. 用 env 的 Python 配置 cmake：`-DCMAKE_INSTALL_PREFIX=$CONDA_PREFIX` +
   `-DPython3_EXECUTABLE=$(which python)` + `-DCMAKE_INSTALL_RPATH='$ORIGIN;...'`
4. Ninja 构建 + 安装
5. **在 `env -i` 干净环境里烟雾测试 `import talosos.runtime`**，确保 RPATH
   干净、不依赖外部 `LD_LIBRARY_PATH`

产物分布：

| 文件 | 位置 |
|---|---|
| `libtalosos.so` / `libzenohc.so` | `$CONDA_PREFIX/lib/` |
| `_talosos_runtime*.so` + `talosos/` 包 | `$CONDA_PREFIX/lib/pythonX.Y/site-packages/` |
| `talos` / `talosos_tool` CLI | `$CONDA_PREFIX/bin/` |

因为全部装进 conda prefix，**`conda activate/deactivate` 自动切换 PATH 与
site-packages**，不需要额外激活钩子；也不需要 `LD_LIBRARY_PATH`，RPATH
会定位同目录的 `libtalosos.so`。

### 怎么选

| 你的情况 | 选 |
|---|---|
| env 用 3.12，只想快速接上 TalosOS | **A** |
| env 锁定了其它 Python 版本 | **B** |
| 多个 env 并存、各自独立 | **B**（每个 env 各运行一次） |
| CI / Docker / 可复制部署 | **B**（写进 `environment.yml` + Dockerfile） |

### 卸载（保留 env）

```bash
# 方案 A：
rm -f $CONDA_PREFIX/etc/conda/activate.d/talosos.sh
rm -f $CONDA_PREFIX/etc/conda/deactivate.d/talosos.sh

# 方案 B：
rm -rf $CONDA_PREFIX/lib/python*/site-packages/talosos
rm -f  $CONDA_PREFIX/lib/libtalosos.so* $CONDA_PREFIX/lib/libzenohc.so
rm -f  $CONDA_PREFIX/bin/talos $CONDA_PREFIX/bin/talosos_tool
```

---

## Python venv 独立环境 { #venv }

没装 conda、想用标准 `python -m venv` 做隔离？走 `install_venv.sh`，行为
与 conda 的方案 B 一致 —— 针对 venv 的 Python 重编一次，产物全部进
`$VIRTUAL_ENV`：

```bash
# 1. 建 venv（系统 python3 的版本决定 ABI）
python3 -m venv ~/venvs/talos
source ~/venvs/talos/bin/activate

# 2. 装 TalosOS
cd /path/to/TalosOS
scripts/install_venv.sh              # 自动 pip install cmake ninja pybind11 pyyaml
scripts/install_venv.sh --clean      # 源码改动后从头重编
```

脚本会：

1. 检查 `$VIRTUAL_ENV` 已激活，拿到 venv 的 Python 版本 + ABI tag
2. 在 venv 里 `pip install` 缺的构建工具：`cmake / ninja / pybind11 / pyyaml`
3. 检测系统 `cargo`，没有就**问你要不要 `rustup` 装**（venv 装不了 cargo，
   只能系统级；`AUTO_INSTALL_RUST=1` 可以跳过提示）
4. 用 venv 的 Python 配 cmake：`-DCMAKE_INSTALL_PREFIX=$VIRTUAL_ENV` +
   `-DPython3_EXECUTABLE=$(which python)` + `-DCMAKE_INSTALL_RPATH='$ORIGIN;...'`
5. 构建 + 安装
6. 在 `env -i` 干净环境里烟雾测试 `import talosos.runtime`

产物分布：

| 文件 | 位置 |
|---|---|
| `libtalosos.so` / `libzenohc.so` | `$VIRTUAL_ENV/lib/` |
| `_talosos_runtime*.so` + `talosos/` 包 | `$VIRTUAL_ENV/lib/pythonX.Y/site-packages/` |
| `talos` / `talosos_tool` CLI | `$VIRTUAL_ENV/bin/` |

因为全部进 venv，**`source activate / deactivate` 自动切换 PATH 与
site-packages**，也不需要 `LD_LIBRARY_PATH`（RPATH 到同目录 libtalosos.so）。

### venv vs conda env 怎么选

| 你的情况 | 选 |
|---|---|
| 机器没装 conda，想轻量 Python 隔离 | **venv** + `install_venv.sh` |
| 需要多套 Python 版本切换 | **conda** + `install_conda.sh` |
| 已经习惯 Anaconda / Miniforge 生态 | **conda** |
| CI / Docker 尽量少依赖 | **venv**（不需要 conda-forge 源） |

### 卸载 venv 里的 TalosOS

```bash
rm -rf $VIRTUAL_ENV/lib/python*/site-packages/talosos
rm -f  $VIRTUAL_ENV/lib/libtalosos.so* $VIRTUAL_ENV/lib/libzenohc.so
rm -f  $VIRTUAL_ENV/bin/talos $VIRTUAL_ENV/bin/talosos_tool
# 或者更干脆：
deactivate && rm -rf ~/venvs/talos
```

---

## 激活环境

=== "bash"

    ```bash
    source /opt/talosos/setup.bash
    # macOS: source /usr/local/talosos/setup.bash
    ```

=== "zsh"

    ```zsh
    source /opt/talosos/setup.zsh
    ```

=== "PowerShell (Windows)"

    ```powershell
    . C:\talosos\setup.ps1
    ```

激活脚本会注入这些环境变量：

| 变量 | 作用 |
|---|---|
| `PATH` / `%PATH%` | 前置 `<prefix>/bin`，让 `talos`、`talosos_tool` 可直接调 |
| `LD_LIBRARY_PATH` (Linux) / `DYLD_LIBRARY_PATH` (macOS) | 前置 `<prefix>/lib`（多数情况下 RPATH 足够，这一项是保险）|
| `PYTHONPATH` | 前置 `<prefix>/lib/pythonX.Y/site-packages` |
| `CMAKE_PREFIX_PATH` | 前置 `<prefix>`，让下游包 `find_package(TalosOS)` |
| `TALOSOS_ROOT` | 指向 prefix，供自定义脚本用 |

## 验证

```bash
talos --version                 # talos 1.0.0
talos --help
which talosos_tool              # <prefix>/bin/talosos_tool

# Python 绑定
python3 -c "from talosos.runtime import Node; print('ok')"

# 跑一个示例
python3 $(dirname $(which talos))/../share/talosos/examples/python/talker.py &
talos topic list
kill %1
```
