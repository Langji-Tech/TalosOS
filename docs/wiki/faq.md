# 常见问题 FAQ · 排障

## 平台兼容性

### 支持哪些操作系统？{#platforms}

| 平台 | 状态 |
|---|---|
| Ubuntu 22.04 / 24.04 | :material-check-bold: 一级支持 |
| Ubuntu 20.04 | :material-check-bold: 可用 |
| Ubuntu 18.04 | :material-check: 需升级 CMake / GCC / Python，见 [安装页](installation.md#ubuntu-1804) |
| macOS 12+ | :material-check: 可用，详见[安装页](installation.md#macos-intel-apple-silicon) |
| WSL2 (Windows) | :material-check-bold: 一级支持，按 Ubuntu 流程 |
| Windows 原生 | :material-alert: 实验性，只建议 C++ DLL 用例 |

### 能在 Python 3.6 上跑吗？{#py36}

**不能直接跑**。Python 3.6 缺 `dataclasses` 标准库 + 部分 typing 特性。
最低要求是 **Python 3.7**（有 dataclasses，18.04 deadsnakes PPA 一条命令
就能装）。如果你必须在 3.6 上跑，用 `pip install dataclasses` 装回填
后大多数模块可用，但未做 CI 回归。

### CMake 版本要求？{#cmake-version}

最低 **CMake 3.16**（与内置 zenoh-c 一致）。18.04 自带 3.10 需要 Kitware
PPA 升级。

### 怎么在 conda env 里用 TalosOS？{#conda}

看 env 的 Python 版本：

- **env 用 Python 3.12** ——写 `activate.d` 钩子把 `/opt/talosos` 接进去，不用重编
- **其它版本** ——`scripts/install_conda.sh` 针对 env 的 Python 重编，产物全进
  `$CONDA_PREFIX`，env 完全自包含

两种方案的完整步骤在[安装页 → Conda 独立环境](installation.md#conda)。
核心约束：pybind11 扩展 ABI 和 Python 版本严格绑定，`.deb` / `install_opt.sh`
打的是 `cpython-312`，别的版本必须重编。

## 安装 & 环境

### `talos: command not found` {#talos-not-found}

`setup.bash` / `setup.zsh` 没 source。

```bash
source /opt/talosos/setup.bash     # bash
source /opt/talosos/setup.zsh      # zsh
which talos                        # → <prefix>/bin/talos
```

### `libzenohc.so: cannot open shared object file` {#libzenohc}

如果你是**手动 cmake** 构建（不是 `talos build`）出来的二进制报这个错，
那说明链接时没拿到 RPATH。

```text
$ readelf -d my_node | grep RUNPATH
  (应该能看到指向 libzenohc.so 所在目录的 RUNPATH)
```

TalosOS 1.0 起已经给 `libtalosos.so` 嵌入 `RUNPATH=$ORIGIN`，
**只要 `libzenohc.so` 和 `libtalosos.so` 在同一目录**就会自动找到 —— 不
需要 `LD_LIBRARY_PATH`。

如果你是从**老版本** `/opt/talosos`（1.0 之前的预发内测）安装的，请重装：

```bash
cd /path/to/TalosOS
scripts/install_opt.sh /opt/talosos
```

### `find_package(TalosOS)` 报 `CMP0144 ... TALOSOS_ROOT`

旧 CMake 警告，不影响构建。用最新 `talos pkg create` 生成的
`CMakeLists.txt` 已加 `cmake_policy(SET CMP0144 NEW)` 把它消掉。

---

## 工作空间 & 构建

### `talos pkg create` 提示没找到 `.talos_ws` {#workspace-init}

ROS1 风格：你不需要手动 `touch .talos_ws`，工具会在当前目录名为 `src`
时自动把父目录标为工作空间。

```bash
mkdir -p ~/ws/src && cd ~/ws/src
talos pkg create my_pkg            # 自动 initialized workspace at ~/ws
```

### `talos build` 成功但 `talos run` 说找不到可执行 {#exe-not-found}

检查 `CMakeLists.txt` 里是否**真正**调用了
`install(TARGETS <exe> RUNTIME DESTINATION lib/${PROJECT_NAME})`。
只有 install 过的目标才会出现在 `<ws>/install/lib/<pkg>/`。

用 `talos pkg create --with-node` 生成的模板已经带了这个 install 规则。
手动建的包要记得加。

### 重新编译后 `talos run` 还跑旧版本

`talos build` 的 install 步骤是增量的；如果你只改了 .cc 而没触发 CMake
重配置，有时会命中缓存。清一下：

```bash
rm -rf ~/ws/build/<pkg> ~/ws/install/lib/<pkg>
talos build <pkg>
```

---

## 通信 & 话题

### `talos topic list` 看不到自己刚发的话题 {#topic-discovery}

zenoh 的 liveliness 发现有 200~500 ms 级别的延迟，**节点刚启动**就立刻
`list` 可能看不到。`--timeout-ms 800` 一般够用：

```bash
talos topic list --timeout-ms 800
```

另：你的话题在代码里用的是**相对名**（如 `"chatter"`），CLI 看到的会是
`/<node_fqn>/chatter`；用**绝对名**（`"/chatter"`）则是 `/chatter`。

### 订阅者收不到消息

优先顺序排查：

1. 订阅者**在发布者之前**启动了吗？zenoh 默认不保留历史，订阅者晚到
   的话前几帧会丢。建议：sub 先起，或用 `talos topic hz` 确认发布端
   确实在发。
2. 订阅的 key **拼对**了吗？检查 `talos topic list` 显示的完整 key。
3. Python 侧：`node.subscribe(...)` 返回值**有没有被保留**？老版本里
   如果立刻丢弃就会析构掉底层 zenoh 订阅器。1.0 起 Node 内部自动托管。

### 局域网另一台机收不到

详见 [LAN 部署](deployment/lan.md)。简要：

- 确认两端**都 source 了 setup 脚本**，`talos --version` 能输出。
- 默认多播要求路由器 / 防火墙允许 `224.0.0.224:7446`。
- Docker / K8s / 云 VPC 通常**关多播**，用 `--mode peer --listen/--connect` 指定
  端口。
- 时钟没同步时 `header.stamp` 不可比，但 pub/sub 仍能传 —— 别被延时
  统计里的负值迷惑。

---

## 图像 / OpenCV

### `cv::imshow` 在 `cv_subscriber` 不出窗口

`$DISPLAY` 没设、或在 SSH 里无 X 转发。示例代码已做回退：检测到
headless 时把前几帧写到 `/tmp/cv_demo_frame_*.png` 方便你离线对比。

### `talos::adapters::ToCvMat(msg)` 返回的 Mat 回调外用崩了 {#cv-lifetime}

这个 `Mat` 是**对 `msg.data` 的零拷贝视图**；回调退出后 payload 就被
释放了。需要跨回调保留数据：

```cpp
cv::Mat kept = talos::adapters::ToCvMat(msg).clone();   // 改 clone
```

---

## 性能

### 10 路图像同时发延时比预期高

参考 [性能基准页](reference/benchmarks.md)。常见原因：

- 用的是 `talos plot/viz` 的 matplotlib 管线，**渲染本身就 20–40 ms/帧**，
  不是传输延时。**测协议用 `image_bench --role sub`**，它是纯 C++。
- 发布/订阅在**同一进程** (`--role both`)：zenoh 在有 SHM fast path 的
  情况下会走共享内存，但同 Session 内的发布可能因内部调度异步化带来
  额外 1–2 ms。两进程能更真实反映 wire 路径。
- payload 走 raw `Image`（~1 MB/帧）时单路就近 1 MB × N Hz，吃带宽。
  选 `CompressedImage + jpg q=85` 通常压 10× 以上。

### CPU 占用高

`talos topic echo`、`plot`、`viz` 都会反序列化每一帧，heavy msg 下 CPU
占用明显。生产节点里请**直接用运行时 API**，不要长期挂 `echo`。

---

## Python

### `from talosos.runtime import Node` 报 `ImportError: _talosos_runtime`

运行时扩展 .so 没编出来。重装时确认 `pybind11` 已装：

```bash
pip install --user --break-system-packages pybind11
scripts/install_opt.sh /opt/talosos
```

### 回调里抛异常被吞了

为了不让一次失败杀掉整个 zenoh 后台线程，订阅/服务回调的异常被打到
stderr 后**静默吞掉**。调试时把异常信息自己打出来、或者用
`try/except` 捕获后 `raise SystemExit(...)`。

---

## Wiki

### 本地预览 / 二次开发本文档

```bash
cd docs/
python3 -m mkdocs serve      # 浏览器打开 http://127.0.0.1:8000
python3 -m mkdocs build      # 产出静态站到 ../site/
```

### 想改配色 / 排版

走 `wiki/assets/extra.css`（已用作主题扩展）。所有 CSS 变量都在文件顶
部，改一下即可得到不同风格的科技感。
