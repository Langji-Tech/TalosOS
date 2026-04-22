# TalosOS

> ROS1-style robotics OS on top of **zenoh-cpp**. C++ + Python, CDR 字节兼容
> ROS2，GPU-accelerated 3D viz，`.deb` 一键安装。
>
> 由 **杭州朗极智能科技有限公司 (Hangzhou Langji Intelligent Technology
> Co., Ltd.)** 出品。

<p align="center">
  <img alt="cpp" src="https://img.shields.io/badge/C%2B%2B-17-blue">
  <img alt="python" src="https://img.shields.io/badge/Python-3.7%2B-blue">
  <img alt="cmake" src="https://img.shields.io/badge/CMake-3.16%2B-green">
  <img alt="platforms" src="https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20WSL2-lightgrey">
  <img alt="version" src="https://img.shields.io/badge/version-1.0.0-brightgreen">
</p>

---

## 为什么还要再做一个机器人 OS

| 维度 | ROS 1 | ROS 2 | **TalosOS** |
|---|---|---|---|
| 传输层 | Custom TCPROS / UDPROS | DDS（厂商繁多） | **zenoh** — 现代、省 CPU、原生 LAN 发现 |
| 消息编码 | 自有 | CDR | **CDR**（ROS2 字节兼容，互发消息不用桥） |
| API 风格 | **ROS1 风**（简单） | `rclcpp`（略重） | **ROS1 风** —— `node->Advertise<T>("topic")` |
| Python 绑定 | `rospy` | `rclpy` | `talosos.runtime`（pybind11，共享 C++ 运行时） |
| 3D 可视化 | `rviz` | `rviz2` | 内置 `talos viz` —— pyqtgraph + OpenGL GPU |
| 安装 | apt | apt / colcon | **`sudo apt install ./talosos_1.0.0-*.deb`** 或源码 |
| 跨网段发现 | master | discovery | zenoh liveliness + 同网 multicast |
| 打包重量 | 几 GB | 几 GB | **<30 MB** `.deb` |

核心主张：**ROS1 的易用 + ROS2 的 wire 兼容 + 2020 年代传输层的性能**。

---

## 功能一览

- **ROS1 风 API**：`talos::Node::Create` + `Advertise<T>` / `Subscribe<T>` +
  `AdvertiseService<Req,Resp>` + 头 only `ActionServer/Client`
- **字节级兼容 ROS2**：CDR 小端封装；你可以用 `rosbag2` 录包、TalosOS 订阅
- **双语言**：C++（主体）+ Python（`talosos.runtime` 由 pybind11 共享 `.so`）
- **三种日志风格**：glog 流（`TALOS_LOG(INFO) << ...`）、ROS1
  流（`TALOS_INFO_STREAM`）、printf（`TALOS_INFO("fmt", ...)`），彩色 +
  时间戳 + 文件行号
- **自定义消息**：反射宏 `TALOS_MESSAGE_FIELDS(a, b, c)`（单包内）或 `.msg`
  代码生成（跨语言跨包）—— 两者 wire 字节一致
- **第三方桥**：`cv_bridge` 等价适配器（`talosos/adapters/opencv.h`）、
  Eigen、PCL
- **完整 CLI**：`talos pkg / build / run / launch / topic / service / plot /
  viz / rqt`
- **GPU 3D 可视化**：`talos viz` 打开 RViz 风单一 3D 场景，话题作为图层
  叠加 —— PointCloud2 / LaserScan / Pose / TF / Marker / OccupancyGrid /
  Octomap 全覆盖
- **局域网自动发现**：zenoh liveliness，跨设备零配置
- **`.deb` 发布**：Ubuntu 20.04 / 22.04 / 24.04 各一版，安装前缀
  `/opt/talosos`
- **多平台**：Ubuntu 18.04+ / Debian / Fedora / macOS 12+ / WSL2 / Windows
  （实验）
- **conda 支持**：`scripts/install_conda.sh` 针对 conda env Python 编译进
  `$CONDA_PREFIX`

---

## 装起来

### 一键 `.deb`（Ubuntu 20.04+ 最省事）

```bash
# 选与当前 Ubuntu 代号匹配的 .deb（.deb 与 codename + Python ABI 绑定）
wget https://.../talosos_1.0.0-$(lsb_release -cs)_$(dpkg --print-architecture).deb
sudo apt install ./talosos_1.0.0-*_amd64.deb
source /opt/talosos/setup.bash           # or setup.zsh
talos --version                           # → talos 1.0.0
```

### 源码安装（任意平台）

**必备依赖**：CMake 3.16+、C++17 编译器、Rust（`cargo`，zenoh-c 编译用）、
Eigen3、Python 3.7+、pybind11、PyYAML。缺任何一个 `scripts/install_opt.sh`
都会在 `[0/3] checking prerequisites` 立刻报错并列出修复命令。

Ubuntu / Debian 一键把依赖装齐：

```bash
sudo apt install -y build-essential cmake pkg-config libeigen3-dev \
                    python3 python3-pip python3-yaml \
                    python3-matplotlib python3-pyqt5 libopencv-dev
python3 -m pip install --user --break-system-packages \
    pybind11 pyyaml pyqtgraph PyOpenGL

# Rust（zenoh-c 必需，apt 的 cargo 通常太旧，用 rustup）
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"
```

然后构建安装：

```bash
git clone git@github.com:Langji-Tech/TalosOS.git && cd TalosOS
scripts/install_opt.sh                    # → /opt/talosos
source /opt/talosos/setup.bash
talos --version
```

macOS (Homebrew)：

```bash
brew install cmake eigen pkg-config python rust opencv pyqt@5
python3 -m pip install --user pybind11 pyyaml pyqtgraph PyOpenGL
scripts/install_opt.sh                    # → /usr/local/talosos
```

详见 [安装文档](docs/wiki/installation.md)（含 Ubuntu 18.04 / Fedora /
WSL2 / Windows / conda env 各种场景）。

---

## Hello world

```bash
mkdir -p ~/ws/src && cd ~/ws/src
talos pkg create hello --with-node
```

`~/ws/src/hello/src/hello_node.cc`：

```cpp
#include "talosos/logging.h"
#include "talosos/messages.h"
#include "talosos/node.h"

int main(int argc, char** argv) {
  talos::Init(argc, argv);
  auto node = talos::Node::Create("hello");
  auto pub = node->Advertise<talos::msgs::String>("chatter");
  while (talos::Ok()) {
    talos::msgs::String msg; msg.data = "hello from talos";
    pub.Publish(msg);
    TALOS_LOG(INFO) << "publish: " << msg.data;
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
  }
}
```

```bash
cd ~/ws && talos build hello && talos run hello hello_node
```

另起一个终端：

```bash
talos topic echo /hello/chatter
#  data: "hello from talos"
#  data: "hello from talos"
#  ...
```

等价 Python 版（与 C++ **同步兼容**，数据可跨语言流动）：

```python
from talosos.runtime import Node, init, ok
from talosos.messages import String
import time
init()
node = Node.create("hello_py")
pub = node.advertise("chatter", String)
while ok():
    pub.publish(String(data="hello from py"))
    time.sleep(0.5)
```

---

## 3D 可视化（viz / rqt）

```bash
# 随手跑两个 demo 发布器
python3 examples/python/pointcloud_publisher.py &
python3 examples/python/random_gridmap_publisher.py --walls --animate &
python3 examples/python/random_octomap_publisher.py --rebuild &

# 打开统一 3D 场景，双击左侧话题名把它加为图层
talos viz
```

- **统一 3D 视口** —— 像 RViz 一样，多话题叠在一个相机里
- **GPU 硬件渲染** —— pyqtgraph + OpenGL，百万点级点云流畅
- **Turbo 配色** + **Shift+左键平移** + **点大小滑块** + **图层 +/× 切换**
- 已支持图层：PointCloud2 / LaserScan / PoseStamped / TransformStamped /
  Marker / MarkerArray / OccupancyGrid / Octomap / OctomapWithPose
- 渲染节拍锁 30 FPS（`RENDER_TICK_MS = 33`），后台 sampler 全速收数据

多面板 dashboard（含 IMU / Twist / Scalar 曲线等 2D 类型）：`talos rqt`。

---

## 仓库结构

```
TalosOS/
├── include/talosos/            公共 C++ 头（Node / Publisher / Service / Action）
│   ├── msgs/                   std / geometry / sensor / nav / tf2 / viz / pcl / octomap
│   ├── adapters/               cv_bridge / Eigen / PCL 桥
│   ├── serialization.h         cdr::Writer/Reader + TALOS_MESSAGE_FIELDS
│   └── logging.h               彩色日志，三种风格
├── src/                        运行时 + talosos_tool + pybind11 bindings
├── python/talosos/             talos CLI + runtime + 消息 dataclass
├── cmake/                      TalosOSConfig / TalosMessages + deb hook
├── examples/cpp/               talker / listener / class_demo / image_bench /
│                               add_two_ints / fibonacci / opencv_demo
├── examples/python/            与 C++ 一一对应 + pcl_publisher/saver / octomap demo
├── docs/wiki/                  MkDocs Material 文档
├── scripts/                    install_opt.sh / install_conda.sh / make_deb.sh
├── docker/                     跨版本打 .deb 的 Dockerfile
└── zenoh-cpp/                  bundled transport
```

---

## 文档

- **入门**：[安装](docs/wiki/installation.md) · [Cheatsheet](docs/wiki/cheatsheet.md)
- **教程** (C++ / Python 双栏)：
  - [功能包与构建](docs/wiki/tutorials/packages.md)
  - [示例一 · 话题编程](docs/wiki/tutorials/topic.md)
  - [示例二 · 服务编程](docs/wiki/tutorials/service.md)
  - [示例三 · 动作编程](docs/wiki/tutorials/action.md)
  - [示例四 · 自定义消息](docs/wiki/tutorials/custom-messages.md)
  - [示例五 · 图像传输 / cv_bridge](docs/wiki/tutorials/image-transport.md)
  - [示例六 · 点云传输](docs/wiki/tutorials/pointcloud-io.md)
  - [示例七 · 其他数据类型](docs/wiki/tutorials/more-data.md)
  - [Launch 启动文件](docs/wiki/tutorials/launch.md)
  - [rqt / viz 工具箱](docs/wiki/tutorials/rqt.md)
- **参考手册**：[CLI](docs/wiki/reference/cli.md) · [消息](docs/wiki/reference/messages.md) ·
  [架构](docs/wiki/reference/architecture.md) · [性能基准](docs/wiki/reference/benchmarks.md)
- **排障**：[FAQ](docs/wiki/faq.md)
- **AI 编程助手**：[AGENTS.md](AGENTS.md)

本地预览：

```bash
cd docs && python3 -m mkdocs serve      # http://127.0.0.1:8000
```

---

## 测试与基准

```bash
# 图像延时 / 丢帧基准
./build/examples/cpp/image_bench/image_bench --role pub --topics 4 --hz 30 &
./build/examples/cpp/image_bench/image_bench --role sub --topics 4 --report 2.0
# → rx=302 rate=30.02Hz drops(seq)=0 lat_ms p50=1.8 p99=4.7

# 消息 CDR round-trip 自测
python3 examples/python/class_demo.py --roundtrip
```

详见 [性能基准文档](docs/wiki/reference/benchmarks.md)。

---

## 版本 / 兼容性

- 当前版本：**1.0.0**
- API / wire 格式 / 安装布局视为稳定承诺（`CHANGELOG.md` 记录每一条变更）
- 最低要求：**C++17** / **CMake 3.16** / **Python 3.7**（推荐 3.10+）

---

## 贡献

- Bug / feature → GitHub Issues
- PR 前请：
  - `talos build` 通过（所有 examples 都能编译）
  - 新增消息类型必须给出 C++ read/write + Python dataclass + writer，并附一条
    CDR round-trip 单测
  - 改到 `docs/wiki/**` 的请在本地跑过 `mkdocs build`

## 许可

© 2026 杭州朗极智能科技有限公司 · Hangzhou Langji Intelligent Technology Co., Ltd.

开源协议即将在正式公开发布时随仓库发布；在此之前请联系朗极智能团队获取
内部使用 / 商业合作许可。

## 致谢

- [zenoh](https://zenoh.io/) —— 下一代 pub/sub 传输
- [pyqtgraph](https://pyqtgraph.org/) —— GPU 3D 可视化
- ROS 社区 —— CDR 消息约定与 API 风格的灵感来源
