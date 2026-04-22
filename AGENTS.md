# AGENTS.md — AI 编程助手指南

> 这份文档专门写给 **AI 编程助手**（Claude Code / Cursor / Copilot /
> Cody / Aider 等）看，目标是让 AI 在这个仓库中生成的代码**第一次就能
> 编译通过、第一次就能跑起来**。
>
> 如果你是人类读者，请优先阅读 [`docs/wiki/index.md`](docs/wiki/index.md)。

## 0. 一句话项目画像

TalosOS = 基于 `zenoh-cpp` 的 ROS1 风格机器人操作系统（杭州朗极智能科技有限公司出品），
提供 C++ + Python 双语言的 Node / Publisher / Subscription / Service /
Action，消息用 ROS2 兼容的小端 CDR 编码，安装前缀通常是 `/opt/talosos`，
CLI 叫 `talos`，命令集 `pkg / build / run / topic / service / launch /
plot / viz / rqt`。

## 1. 仓库速览

```
TalosOS/
├── include/talosos/              ← 公共 C++ 头
│   ├── node.h, service.h         ← Node / Publisher / Subscription / Service / Client
│   ├── action.h                  ← header-only action server/client
│   ├── messages.h                ← 聚合 umbrella 头
│   ├── msgs/{std,geometry,sensor,nav,tf2,viz,pcl,octomap}_msgs.h
│   ├── serialization.h           ← cdr::Writer / cdr::Reader + TALOS_MESSAGE_FIELDS
│   ├── logging.h                 ← TALOS_LOG(INFO) << ... 等彩色日志
│   └── adapters/{opencv,eigen,pcl}.h  ← 第三方库桥
├── src/                          ← 运行时 + talosos_tool + pybind11 bindings
├── python/talosos/               ← talos CLI + runtime + 消息 dataclass
├── cmake/                        ← TalosOSConfig / TalosMessages / setup scripts
├── examples/cpp/                 ← talker, listener, class_demo, opencv_demo,
│                                     image_bench, add_two_ints, fibonacci
├── examples/python/              ← 等价 Python 示例 + class_demo + 点云/栅格/
│                                     octomap demo publisher + pcl_publisher/saver
├── docs/wiki/                    ← 用户文档 (MkDocs Material)
└── scripts/
    ├── install_opt.sh            ← 一键装到 /opt/talosos（系统范围）
    ├── install_conda.sh          ← 针对 conda env 的 Python 重编安装到 $CONDA_PREFIX
    └── make_deb.sh               ← 打 Ubuntu 当前 codename 的 .deb
```

**你生成的用户代码都住在**：`~/ws/src/<pkg>/src/*.cc` 或 `*.py`。
仓库本身只在你需要改 TalosOS 内部时才动。

## 2. 用户的标准工作流

**绝对按这个顺序**生成操作步骤，不要自造变体：

```bash
# 0. 安装一次（如果 /opt/talosos 已有就跳过）
scripts/install_opt.sh /opt/talosos            # 需要 sudo
source /opt/talosos/setup.bash                 # 或 setup.zsh

# 1. 新建工作空间 + 功能包
mkdir -p ~/ws/src && cd ~/ws/src
talos pkg create my_pkg --with-node            # 自动 init .talos_ws

# 2. 构建
cd ~/ws
talos build my_pkg                             # 或 talos build 全部

# 3. 运行
talos run my_pkg my_pkg_node
```

**不要**教用户：手动 `touch .talos_ws`、手动改 `LD_LIBRARY_PATH`、
`find_package(TalosOS)` 之外的自造 CMake 逻辑。

## 3. 核心 API (C++)

### 3.1 包骨架

新建 `my_pkg/src/my_pkg_node.cc`：

```cpp
#include "talosos/logging.h"
#include "talosos/messages.h"
#include "talosos/node.h"

int main(int argc, char** argv) {
  talos::Init(argc, argv);
  auto node = talos::Node::Create("my_pkg_node");
  TALOS_LOG(INFO) << "my_pkg_node online";
  node->Spin();                                 // 阻塞直到 Ctrl+C
  return 0;
}
```

`my_pkg/CMakeLists.txt`（`talos pkg create --with-node` 已生成）：

```cmake
cmake_minimum_required(VERSION 3.22)
project(my_pkg VERSION 0.0.1 LANGUAGES CXX)
if(POLICY CMP0144)
  cmake_policy(SET CMP0144 NEW)
endif()
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(TalosOS REQUIRED)

add_executable(my_pkg_node src/my_pkg_node.cc)
target_link_libraries(my_pkg_node PRIVATE TalosOS::talosos)
install(TARGETS my_pkg_node RUNTIME DESTINATION lib/${PROJECT_NAME})
```

### 3.2 发布 / 订阅

```cpp
// 发布
auto pub = node->Advertise<talos::msgs::String>("chatter");
talos::msgs::String m; m.data = "hi";
pub.Publish(m);

// 订阅 — 三种等价形式：

// (a) 成员函数指针（最简洁，T 自动推导）
auto sub = node->Subscribe("chatter", &MyClass::OnChatter, this);

// (b) lambda（T 需写出）
auto sub = node->Subscribe<talos::msgs::String>(
    "chatter", [this](const talos::msgs::String& m) { OnChatter(m); });

// (c) std::bind（遗留）
auto sub = node->Subscribe<talos::msgs::String>(
    "chatter", std::bind(&MyClass::OnChatter, this, std::placeholders::_1));
```

**成员变量用非模板类型**：`talos::Publisher pub_;` / `talos::Subscription sub_;`（**不**是 `Publisher<T>`，API 自 1.0 起已类型擦除）。

话题命名规则：
- `"/abs"` → 绝对（zenoh key：`abs`）
- `"rel"` → 相对于 `<ns/node_name>/rel`
- `"~/priv"` → 显式私有，等价 `"rel"`

### 3.3 服务

```cpp
// 用反射宏定义 Req / Resp：
struct AddReq  { int64_t a = 0, b = 0; TALOS_MESSAGE_FIELDS(a, b) };
struct AddResp { int64_t sum = 0;      TALOS_MESSAGE_FIELDS(sum) };

// 服务端
auto svc = node->AdvertiseService<AddReq, AddResp>(
    "/add", &MyClass::OnAdd, this);              // 或传 lambda / std::function

// 客户端
auto client = node->CreateServiceClient<AddReq, AddResp>("/add");
AddReq req{3, 4}; AddResp resp;
if (client.Call(req, resp, std::chrono::seconds(1))) {
  TALOS_LOG(INFO) << "sum=" << resp.sum;
}
```

成员类型 `talos::Service` / `talos::ServiceClient`（也去模板）。

### 3.4 动作 Action

```cpp
#include "talosos/action.h"

using Server = talos::ActionServer<Goal, Feedback, Result>;

auto server = talos::MakeActionServer<Goal, Feedback, Result>(
    node, "/my_action",
    [](Server::Handle& h) {
      for (int i = 0; i < h.goal().count; ++i) {
        if (h.canceling()) {
          Result r; return std::make_pair(talos::GoalStatus::kCanceled, r);
        }
        Feedback fb; fb.progress = i;
        h.PublishFeedback(fb);
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
      }
      Result r;
      return std::make_pair(talos::GoalStatus::kSucceeded, r);
    });

auto client = talos::MakeActionClient<Goal, Feedback, Result>(node, "/my_action");
auto handle = client.SendGoal(Goal{10},
    [](const Feedback& fb){ /* ... */ });
Result out; talos::GoalStatus st;
handle->WaitForResult(out, st);
```

## 3.5 定时 / 计时

头文件 `talosos/rate.h`、`talosos/timer.h`（都是 header-only）：

```cpp
#include "talosos/rate.h"
#include "talosos/timer.h"

// 定频循环
talos::Rate rate(50.0);                // 50 Hz
while (talos::Ok()) { DoStep(); rate.Sleep(); }

// 周期回调（后台线程）
talos::Timer ctrl(100.0, [this]{ OnControl(); });        // 100 Hz（double = Hz）
talos::Timer delay(std::chrono::seconds(3),
                     [this]{ FinishWarmup(); },
                     /*oneshot=*/true);                     // 3 秒后一次
// 析构自动 cancel+join；Cancel() 手动停止也行

// 秒表
talos::Stopwatch sw;
HeavyWork();
TALOS_LOG(INFO) << "took " << sw.milliseconds() << " ms";

// MATLAB 风
talos::Tic();
Work();
double s = talos::Toc();               // 秒；每线程独立

// RAII 自动打印
{ TALOS_SCOPED_TIMER("load image"); ...; }
// → [load image] 12.3 ms
```

**C++ `Timer(double, cb)` 是 Hz**；想按秒用 `Timer(std::chrono::milliseconds(50), cb)`。
**Python `Timer(period_sec, cb)` 是秒**（对齐 `threading.Timer`）。别搞反。

## 4. 日志

三种写法都行，**优先用 glog 风格**（最易读）：

```cpp
TALOS_LOG(INFO)   << "count=" << count;               // 推荐
TALOS_INFO_STREAM("count=" << count);                  // ROS1 风格
TALOS_INFO("count=%lld", static_cast<long long>(n));   // printf
```

等级：`DEBUG INFO WARN ERROR FATAL`。运行时过滤时 `TALOS_LOG(DEBUG) << ...` **编译为 `(void)0`**，零开销。彩色 + 时间戳 + 文件行号由库自动处理。

## 5. 消息目录

直接 `#include "talosos/messages.h"` 拿到所有消息。用到哪些类型就 `talos::msgs::<Name>`：

- `std_msgs`：Header, Empty, String, Bool, Int{8,16,32,64}, UInt{...}, Float32, Float64, ColorRGBA, MultiArray\*
- `geometry_msgs`：Vector3, Point, Point32, Quaternion, Pose{,Stamped}, Pose2D, Twist{,Stamped}, Accel{,Stamped}, Wrench{,Stamped}, Inertia{,Stamped}, Polygon{,Stamped}, Transform{,Stamped}, Pose/Twist/Accel-WithCovariance{,Stamped}
- `sensor_msgs`：Imu, Image, CompressedImage, CameraInfo, RegionOfInterest, LaserScan, PointField, PointCloud2, PointCloud, ChannelFloat32, JointState, NavSatStatus, NavSatFix, Range, Temperature, RelativeHumidity, FluidPressure, Illuminance, MagneticField, TimeReference, BatteryState, Joy
- `nav_msgs`：Path, Odometry, MapMetaData, OccupancyGrid, GridCells
- `tf2_msgs`：TFMessage
- `visualization_msgs`：Marker, MarkerArray, ImageMarker, MenuEntry
- `pcl_msgs`：PointIndices, ModelCoefficients, Vertices, PolygonMesh
- `octomap_msgs`：Octomap, OctomapWithPose

**消息里的字段名全是 snake_case 字段 / 直接访问**（没有 setter）。

## 6. 自定义消息

**两条路径，别混**：

### 6.1 反射宏（单包内、不跨语言时首选）

```cpp
#include "talosos/serialization.h"
#include "talosos/messages.h"

struct MyMsg {
  talos::msgs::Header header;
  float voltage = 0.f;
  std::vector<float> cells;
  TALOS_MESSAGE_FIELDS(header, voltage, cells)   // 字段顺序 == wire 顺序
};
```

### 6.2 `.msg` 代码生成（ROS 风格，跨语言 / 跨包复用首选）

`my_pkg/msg/Foo.msg`：

```
Header header
string name
int32 count
float64[3] fixed_arr
float64[] dynamic_arr
uint8 CONST=5
```

`my_pkg/CMakeLists.txt`：

```cmake
find_package(TalosOS REQUIRED)                   # 自动 include TalosMessages.cmake

talosos_add_messages(
  NAME my_pkg_msgs
  FILES
    msg/Foo.msg
)

add_executable(my_node src/my_node.cc)
target_link_libraries(my_node PRIVATE TalosOS::talosos my_pkg_msgs_msgs)
```

用的时候 `#include "talos/my_pkg_msgs/Foo.h"` → `talos::my_pkg_msgs::Foo`。

## 7. OpenCV bridge (ROS cv_bridge 的 TalosOS 版)

```cpp
#include <opencv2/opencv.hpp>
#include "talosos/adapters/opencv.h"

cv::Mat bgr = cv::imread("x.png", cv::IMREAD_COLOR);

// mat → Image  （encoding 自动从 mat.type() 推导）
auto msg = talos::adapters::ToImageMessage(bgr, header);

// Image → Mat  （零拷贝视图，**别在回调返回后使用！**要用就 clone()）
cv::Mat view = talos::adapters::ToCvMat(msg);

// JPEG / PNG 压缩
auto jpg  = talos::adapters::ToCompressedImageMessage(bgr, "jpg", header,
                 {cv::IMWRITE_JPEG_QUALITY, 85});
cv::Mat m = talos::adapters::ToCvMat(jpg);        // cv::imdecode
```

`my_pkg/CMakeLists.txt` 需要 `find_package(OpenCV COMPONENTS core imgcodecs imgproc highgui)` 并把 `${OpenCV_LIBS}` 加入 `target_link_libraries`。

## 8. Python API

```python
from talosos.runtime import Node, NodeOptions, init, ok, spin
from talosos.messages import Float64, Imu, CompressedImage, PoseStamped

init()
node = Node.create("py_node")

# 发布 / 订阅
pub = node.advertise("/chatter", Float64)
pub.publish(Float64(data=3.14))

sub = node.subscribe("/chatter", Float64, lambda m: print(m.data))
#   ↑ 返回的 Subscription 会被 Node 自动托管；不必自己保留引用

# 服务端
def handler(req): return Float64(data=req.data * 2)
svc = node.advertise_service("/doubler", Float64, Float64, handler)

# 服务客户端
client = node.create_service_client("/doubler", Float64, Float64)
resp = client.call(Float64(data=21.0), timeout_ms=2000)

node.spin()
```

Python 运行时模块是 pybind11 编译产物 `talosos._talosos_runtime`，**不要**
直接 `import zenoh`；统一走 `talosos.runtime`。

### 8.1 Python 端能发的消息类型（有 CDR writer）

以下类型在 `runtime._WRITERS_BY_CLASS` 注册，**既能订阅也能发布**：

- 全部 scalar wrapper（`String / Bool / Int{8..64} / UInt{8..64} / Float32/64`）
- `PoseStamped`, `TwistStamped`, `TransformStamped`, `TFMessage`
- `Image`, `CompressedImage`
- `Imu`
- `LaserScan`, `PointCloud2`
- `Marker`, `MarkerArray`
- `OccupancyGrid`（+ `MapMetaData`）
- `Octomap`, `OctomapWithPose`

**其它类型目前只能订阅（有 read，无 write）**，比如
`Odometry`、`Path`、`JointState`、`CameraInfo`、`NavSatFix`、`Range`、
`Temperature`、`BatteryState`、`PoseWithCovariance*`、`*MultiArray`、
`Polygon`、`ImageMarker`、`MenuEntry`、`PointIndices`、`PolygonMesh` 等。

用户要用它们做 Python publisher：告诉他按以下模板在 `runtime.py` 里加一个
`_w_<name>`（参照 `_w_occupancy_grid` / `_w_octomap`）注册进
`_WRITERS_BY_CLASS`，字段顺序必须与对应 C++ `Write(cdr::Writer&, T const&)`
完全一致。

### 8.2 Python Action

**暂不支持** —— `runtime.py` 没暴露 `ActionServer/Client`。Python 需要时请
用 4 条 topic 手搭（`<action>/goal / feedback / result / cancel`）。给用户
写代码前先提示这一点，再给示例。

### 8.3 conda env 支持

`/opt/talosos` 的 pybind11 扩展是 `cpython-312`，ABI 与 Python 版本强绑定。
三种情况：

- conda env 用 Python 3.12 → `activate.d` 钩子挂 `PYTHONPATH / LD_LIBRARY_PATH`
- 其它 Python 版本 → `scripts/install_conda.sh` 重编到 `$CONDA_PREFIX`
- 不知道怎么选 → 参考 `docs/wiki/installation.md#conda`

## 9. 启动多进程（Launch）

`my_pkg/launch/demo.launch.yaml`：

```yaml
nodes:
  - name: a
    package: my_pkg
    executable: my_pkg_node
    args: ["--rate", "10"]
    env:
      TALOS_LOG_COLOR: "1"
  - name: b
    package: my_pkg
    executable: another_node
```

跑法：

```bash
talos launch my_pkg demo.launch.yaml
talos launch my_pkg demo.launch.yaml --dry-run
```

Ctrl+C 优雅收 SIGINT → SIGTERM → SIGKILL。

## 10. CLI 作弊表

```bash
talos pkg create <name> [--with-node]
talos pkg list [--verbose] [--json]
talos build [pkgs...] [-j N]
talos run <pkg> <exe> [args...]

talos topic list [--verbose]
talos topic echo <key> [--count N]
talos topic hz <key>   [--window S]
talos topic bw <key>
talos topic pub <key> --utf8 "STR"  |  --hex HEX
talos topic info <key>

talos service list
talos service info <key>
talos service call <key> --hex HEX   [--timeout-ms 3000]

talos launch <file>
talos launch <package> <launch_file>

talos plot <topic> --type <Type> --field a.b.c

# viz —— 两种模式：
talos viz                                 # 无参数：打开 RViz 风 3D dashboard
                                           #   左侧列出可 3D 可视化的话题
                                           #   点 + 加入为图层，× 移除
                                           #   右侧单一 3D 视口、共享相机
talos viz <topic> --type <Type>            # 单面板窗口（图像/标量/曲线也行）
talos viz /tf --type TFMessage             # → 文本帧树（无 GUI）

# rqt —— 多面板 dashboard（含 IMU / Twist / 标量曲线等 2D 类型）
talos rqt
```

`talos viz` dashboard 支持图层类型：PointCloud2 / LaserScan / PoseStamped /
TransformStamped / Marker / MarkerArray / **OccupancyGrid**（XOY 贴图，像
RViz Map）/ **Octomap / OctomapWithPose**（真 3D 彩色立方体体素，`id="talos_voxels_v1"`
的 demo 格式；真 OctoMap 二叉树解码尚未实现）。

渲染节拍锁 **~30 FPS** —— 常量 `rqt.RENDER_TICK_MS = 33` 统一控制所有 UI
tick timer。改这个值就整体改帧率，不要在局部改。

网络相关参数：`--mode peer|client|router --connect ENDPOINT --listen ENDPOINT --no-multicast`。所有 CLI 子命令都支持。

## 11. 你给用户生成代码时的常见陷阱 ⚠️

别踩：

1. **`Publisher<T>` / `Subscription<T>` 类型已去模板**：成员声明写 `talos::Publisher pub_;`，不是 `talos::Publisher<Msg> pub_;`。
2. **`ToCvMat(msg)` 是零拷贝视图**：回调外使用必须 `clone()`。
3. **话题名带前导 `/`** 视作绝对，**不带**视作相对。CLI 输出永远带 `/`，代码里建议也用绝对以避免命名空间歧义。
4. **Python 订阅返回值**不需要手动保留；但 **lambda 捕获**里出现的 `self` 要保证 `self` 本身有长生命周期。
5. **服务 Request / Response 必须有至少一个字段**（CDR 限制）。若语义上“无参”，用 `talos::msgs::Empty`（内部是一字节 pad）。
6. **Action feedback 写在 `h.PublishFeedback(...)`，不是 return 里**。return 的 pair 只负责 final status + Result。
7. **`find_package(TalosOS)` 之后**，`talosos_add_messages()` 函数已经自动可用，不要再手动 `include(TalosMessages.cmake)`。
8. **别** `sudo apt install ros-* cv_bridge`；TalosOS 的 cv_bridge 就是 `include/talosos/adapters/opencv.h`。
9. **别** 把用户引向 `/opt/talosos` 的 `setup.bash` 之外的环境激活方式；不要手动在 `~/.bashrc` 加 `LD_LIBRARY_PATH`。
10. **别** 建议用户写 `TALOS_INFO("%s", obj)` —— `%s` 需要 `c_str()`。不确定时用 `TALOS_LOG(INFO) << obj`，**流式永远安全**。
11. **消息字段顺序 == wire 顺序**。改 `TALOS_MESSAGE_FIELDS(a, b, c)` 里的顺序等于修改 wire 协议，不要随意换。
12. **Python dataclass 消息**：对应 C++ 消息的字段名和顺序**必须一一对应**。否则 CDR 解码会错位。
13. **rqt / viz 的 3D 面板**需要 `pyqtgraph + PyOpenGL`。没装会静默回退到
    matplotlib 软件 3D（慢得多）。给用户推荐：`pip install --user pyqtgraph PyOpenGL`。
14. **`talos viz` 不再强制要 topic + type**。无参数 = 打开 dashboard。别教
    用户必须带 `--type`。
15. **OccupancyGrid.data 的字节语义**：`-1` = 未知、`0` = 自由、`1..100` =
    占据概率 (%)。Python 侧用 `numpy.int8` 数组 `.tobytes()` 送入，不要
    混用 uint8 或 clip 到 [0,255]。
16. **Octomap.data 有两种格式**：真实 OctoMap 的二叉树（ROS 通用）**未实现
    解码**；demo 格式 `id="talos_voxels_v1"` = 连续 `float32 x,y,z,size`
    每体素 16 字节。给用户写 publisher 要么用 demo 格式、要么明确说
    "viz 侧会跳过"。

## 12. 最小可运行验证单元

生成完代码，建议跑：

```bash
cd ~/ws
talos build my_pkg -j
talos run my_pkg my_pkg_node &
talos topic list
# 你的话题应当出现
kill %1
```

或更扎实：写一个 `examples/cpp/roundtrip/...`，发一条消息，订阅端打印期望值 —— 对照 `examples/cpp/talker.cc` + `listener.cc`。

## 13. 参考文档

人读的详细版：

- `docs/wiki/index.md` —— 门户
- `docs/wiki/cheatsheet.md` —— 一页 API 速查
- `docs/wiki/tutorials/packages.md` —— 功能包与构建
- `docs/wiki/tutorials/topic.md` —— 示例一 · 话题编程（C++ / Python 双栏）
- `docs/wiki/tutorials/service.md` —— 示例二 · 服务编程
- `docs/wiki/tutorials/action.md` —— 示例三 · 动作编程
- `docs/wiki/tutorials/custom-messages.md` —— 示例四 · 自定义消息
- `docs/wiki/tutorials/image-transport.md` —— 示例五 · 图像传输 / cv_bridge
- `docs/wiki/tutorials/pointcloud-io.md` —— 示例六 · 点云传输（含 PCL/PLY 双向）
- `docs/wiki/tutorials/more-data.md` —— 示例七 · IMU/Scan/TF/Marker/Grid/Octomap
- `docs/wiki/tutorials/launch.md` —— Launch 启动文件
- `docs/wiki/tutorials/rqt.md` —— rqt / viz 工具箱（含 3D 面板、图层、键位）
- `docs/wiki/tutorials/image-bench.md` —— 进阶：图像延时 / 丢帧基准
- `docs/wiki/reference/architecture.md` —— 分层 + mermaid 时序图
- `docs/wiki/reference/messages.md` —— 消息目录
- `docs/wiki/reference/cli.md` —— CLI 全参考
- `docs/wiki/reference/benchmarks.md` —— 性能基准
- `docs/wiki/faq.md` —— 排障大全

!!! note "教程编号变更"

    旧教程文件（`first-pub-sub.md / class-style.md / services.md /
    actions.md / python.md / image-demo.md / opencv-bridge.md`）**已删除**，
    合并进新的"示例 N"系列。引用旧路径的链接要改。

本地浏览：

```bash
cd docs && python3 -m mkdocs serve
# http://127.0.0.1:8000
```

## 14. 你不要做的事

- 不要**编造**不存在的消息类型。若用户要的不在第 5 节列表里，提示他
  按第 6 节自定义或帮他起一个新的 `.msg` 文件。
- 不要**编造** CLI 子命令。第 10 节就是全集。
- 不要**编造**头文件路径。全部公共头在 `include/talosos/`，子头在
  `include/talosos/msgs/` 和 `include/talosos/adapters/`。
- 不要**改**任何与 ROS1/2 兼容相关的 wire layout（CDR encapsulation、
  字段顺序、string null terminator 规则），除非用户**明确**要求。
- 不要**删**现有 setup 脚本里对 `TALOSOS_ROOT` 等环境变量的导出。

---

**文档版本**：对应 TalosOS 1.0 + 1.0.x 可视化增量（RViz 风统一 3D 场景
viz、OccupancyGrid/Octomap 图层、pcl_publisher/pcl_saver、30 FPS 渲染锁、
conda env 安装脚本、Python 端 Image/Imu/Marker/MarkerArray/TF writer）。
若发现与代码实际偏离，**以 `include/talosos/*.h`、`python/talosos/` 和
`examples/` 为准**。
