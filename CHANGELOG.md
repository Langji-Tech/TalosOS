# Changelog

All notable changes to TalosOS are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
observes [Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-04-21 — 首个正式发布

TalosOS 的第一个公开稳定版，API / wire 格式 / 安装布局从此视为稳定承诺。
由 **杭州朗极智能科技有限公司** 出品。

### 亮点

- **ROS1 风格 API、现代 zenoh-cpp 传输层**：Node / Publisher / Subscription /
  Service / Action，C++ + Python 一等公民。
- **CDR wire 兼容 ROS2**：payload 可直接喂 `ros2 bag` / Foxglove Studio。
- **一键 `.deb` 安装** (Ubuntu 20.04 / 22.04 / 24.04)，装到 `/opt/talosos`。
- **`talos` CLI** 九个子命令：`pkg · build · run · topic · service · launch · plot · viz · rqt`。
- **完整 MkDocs 文档**（中文）+ **AI 编程助手文档** `AGENTS.md`。

### Added

- C++ 核心运行时 `libtalosos.so`：Node、Publisher、Subscription、Service、
  ServiceClient、ActionServer、ActionClient、CDR Writer/Reader、彩色日志、
  话题名解析（ROS 风格 `/abs` 与 `relative`）。
- 类型擦除 API：`talos::Publisher` / `talos::Subscription` / `talos::Service`
  等类本身**非模板**，模板只出现在 `Advertise<T>()` / `Subscribe<T>()` /
  `Call(req, resp)` 等调用点。
- 三种等价回调绑定：成员函数指针、lambda、`std::bind`。
- ROS `cv_bridge` 对等物 `include/talosos/adapters/opencv.h` —
  `cv::Mat` ↔ `sensor_msgs::Image` / `CompressedImage` 零拷贝视图 + JPEG/PNG
  codec。
- `TALOS_LOG(LEVEL) << ...` glog 风格流式日志（与 ROS1
  `TALOS_INFO_STREAM` + printf 风格共存）。
- ~60 个内置消息类型，覆盖 std / geometry / sensor / nav / tf2 /
  visualization / pcl / octomap。
- 两种自定义消息路径：
  - `TALOS_MESSAGE_FIELDS(...)` 反射宏 — 单文件、单包内最快。
  - `.msg` 文件 + CMake `talosos_add_messages()` codegen — ROS 风格、
    跨语言 / 跨包复用。
- `talos` CLI (Python)：工作空间 / 包 / 构建 / 运行 / 话题 / 服务 /
  launch / plot / viz / rqt，bash + zsh tab 补全。
- Python 运行时 `talosos.runtime`（pybind11），与 C++ 侧 wire 字节一致。
- 动作 Action：`goal / feedback / cancel / result` 四话题协议 +
  `GoalID` UUID + 8 态 `GoalStatus`，支持并发多 goal。
- `talos launch <file>` YAML 多节点启动，彩色前缀 stdout，SIGINT→SIGTERM
  →SIGKILL 三级回收。
- `talos plot` / `talos viz` / `talos rqt` 实时可视化（matplotlib + PyQt5）。
- zenoh liveliness 自动注册，`talos topic list` / `talos service list`
  实时发现。
- 图像延时压测 `examples/cpp/image_bench/`：10 话题并发下 p50 ≈ 2.5 ms
  (同机 loopback 397 KB PNG)。
- `.deb` 打包（CPack DEB generator）：
  - 前缀 `/opt/talosos`
  - `Depends` 自动用 dpkg-shlibdeps 锁定 libc / libstdc++
  - `Recommends` python3-pybind11 / matplotlib / PyQt5 / OpenCV
  - postinst 自动 `ldconfig` + 友好上手提示
  - Docker build env 支持跨版本打包（`docker/ubuntu-2004-deb.Dockerfile`）
- `scripts/make_deb.sh` 一键打包脚本。
- `scripts/install_opt.sh` 源码一键安装脚本（Linux + macOS）。
- `scripts/install.ps1` Windows 实验性安装脚本。
- 完整 **MkDocs Material** 中文文档 (`docs/wiki/`)：首页、安装、速查卡、
  FAQ、9 篇教程（pub/sub、服务、动作、自定义消息、包管理、launch、rqt、
  Python、image、cv_bridge）、参考手册（CLI、消息、架构、性能）、LAN
  部署、关于页。
- `AGENTS.md` AI 编程助手指南（14 章，含 12 条常见陷阱 + 防幻觉声明）。

### 平台支持

- Ubuntu 22.04 / 24.04：一级支持
- Ubuntu 20.04：可用（源码或 Docker 打 focal deb）
- Ubuntu 18.04：可用（需 Kitware PPA + deadsnakes Python）
- Debian 11+ / Fedora 36+：可用
- macOS 12+：C++ 与 CLI 均可用（`@loader_path` rpath）
- WSL2：一级支持
- Windows 原生：实验性（仅 C++ 库 + MSVC + PowerShell 安装脚本）

### Known limitations

- `.deb` 与 Ubuntu 代号绑定（pybind11 ABI tag 限制）；每个发行版一份
  `.deb`。
- Windows 原生 `talos launch` 信号回收不如 Linux 干净。
- `talos rqt` 目前只有最小 PyQt5 壳（plot + viz 子面板），后续会继续扩
  展插件系统。

---

发布里程碑与责任：
- 规划 / 实现：TalosOS 开发团队
- 维护方：杭州朗极智能科技有限公司 / Hangzhou Langji Intelligent Technology Co., Ltd.
- 贡献指南：随后续 release 补充 `CONTRIBUTING.md`
