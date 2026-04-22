# rqt 工具箱

调试三件套：

- `talos plot` —— 标量字段的实时时序曲线（轻量，matplotlib）
- `talos viz`  —— **3D 场景可视化**（dashboard 只列 3D 类型 / 也支持单面板）
- `talos rqt`  —— **全类型 dashboard**（标量曲线 / IMU / TF 都能开）

`viz` 和 `rqt` 共用同一套面板类，**渲染质量与交互完全一致**；差别在于列表
过滤策略和窗口定位。3D 类型（点云 / 激光 / 位姿 / Marker）走 pyqtgraph +
OpenGL GPU 通道，图像走 Qt pixmap，标量 / IMU / Twist 走 matplotlib 曲线，
TFMessage 打印帧树。

## plot

```bash
talos plot /imu/data --type Imu --field linear_acceleration.z
talos plot /cmd_vel --type TwistStamped --field twist.linear.x --history 400
talos plot /battery/voltage --type Float32
```

字段路径使用点号访问：

| 消息类型      | 示例字段路径                       |
| ------------- | ---------------------------------- |
| Float64       | `data`                              |
| Imu           | `linear_acceleration.x`             |
| TwistStamped  | `twist.angular.z`                   |
| PoseStamped   | `pose.position.x`                   |

默认值：标量包装器默认 `data`；其他消息必须显式 `--field`。

## viz

`talos viz` 是**3D 场景可视化工具**，RViz 风：一个 3D 视口，多个话题作为
图层叠加。两种模式：

### Dashboard 模式（推荐，默认）

```bash
talos viz             # 无参数：打开 dashboard
```

窗口布局：

- **左侧**：自动发现 **可以 3D 可视化的话题**。支持类型：
  `PointCloud2` / `LaserScan` / `PoseStamped` / `TransformStamped` /
  `Marker` / `MarkerArray` / **`OccupancyGrid`** / **`Octomap`** /
  **`OctomapWithPose`**。每行后面是切换按钮：蓝色 **+** 表示未启用、点它
  加入 3D 场景作为图层；变成红色 **×** 后再点即可移除。双击行也等效。
- **右侧**：一个**统一的 3D 场景**占满整个区域 —— 所有已添加的图层共享
  同一个相机、地面网格、原点轴。顶部工具栏：`重置视角` / `网格` / `原点
  轴` / `点大小` 滑块 / 当前 `N 层 · M pts` 状态指示。

图层类型与渲染：

| 消息类型 | 渲染方式 |
|---|---|
| PointCloud2 | GPU 散点，Turbo 按 Z 上色，自动降采样到 200k |
| LaserScan | 射线线段 + 端点散点，按距离 Turbo 上色 |
| PoseStamped / TransformStamped | 轨迹折线 + XYZ=RGB 姿态轴 |
| Marker / MarkerArray | 按 `type` 画 line_strip / line_list / scatter |
| **OccupancyGrid** | **XOY 平面纹理贴图**（像 RViz 的 Map）：未知=深蓝灰半透 / 自由=近白 / 占据=深灰按概率渐变 |
| **Octomap / OctomapWithPose** | **真 3D 立方体体素**（`GLMeshItem` 批量 cube），按 Z 上 Turbo、带边缘线，`id="talos_voxels_v1"` 格式直读 |

交互与 rqt 3D 面板一致：左键拖环绕、**Shift+左键拖平移**、中键平移、滚
轮缩放。点大小滑块作用于**所有云图层**。

选项：

| 选项 | 说明 |
|---|---|
| `--refresh N` | 话题列表刷新间隔秒数（默认 2） |
| `--title "..."` | 自定义窗口标题 |

想要多面板栅格 / 非 3D 类型（标量曲线 / IMU / 相机图像）→ 用 `talos rqt`。

!!! note "为什么单场景而不是多面板？"

    点云 / 激光 / 位姿 / Marker 天然在同一坐标系里，并排多个面板既浪费屏
    幕又割裂场景。RViz 把它们叠在一个视口里，这里也一样 —— 想比较多路
    传感器时直接全开加进去，相机共享就能同步看。

### 单面板模式（脚本友好）

```bash
talos viz /demo/cloud       --type PointCloud2      # GPU 3D 点云
talos viz /demo/scan        --type LaserScan        # GPU 3D 激光
talos viz /camera/image/rgb --type Image            # 图像
talos viz /battery/voltage  --type Float32          # 时序曲线
talos viz /tf               --type TFMessage        # 文本帧树
```

topic + `--type` 同时给就走单面板；窗口顶部信息条会标注当前 renderer：
**`GPU (OpenGL)`** 表示走 pyqtgraph GL 面板；**`CPU (matplotlib)`** 表示回
退到了软件 3D（没装 pyqtgraph 时）。

强制指定后端（一般不用）：

| `--renderer` | 含义 |
|---|---|
| `auto`（默认） | 按 `--type` 选 qt 或 tf |
| `qt` | 强制开 Qt 单面板窗口 |
| `tf` | 强制走文本帧树 |
| `image` / `scan` / `cloud` / `marker` / `pose` | legacy 兼容，内部统一走 qt |

交互键位、工具栏按钮、点大小滑块、turbo 配色等**完全等同于 rqt 的 3D 面板**
（见下文 [3D 面板 GPU 渲染](#gl-panels) 小节）。

**`talos viz` 和 `talos rqt` 的区别：**

- `talos viz`（dashboard 默认）：**只列 3D 类型**，更聚焦场景可视化
- `talos viz /topic --type T`：**单面板**窗口，适合脚本化 / 紧凑调试
- `talos rqt`：**全部类型**的 dashboard，包括标量曲线、IMU、TF 等

三者底层是同一套面板类，渲染质量一致。

## rqt

```bash
talos rqt
```

打开一个 PyQt5 窗口，表单里填写 topic / type / field，两个按钮：

- **Add plot** → 后台启动一个 `talos plot …`
- **Add viz**  → 后台启动一个 `talos viz …`

每个面板都是独立子进程；关闭 rqt 主窗会一并结束这些子进程。适合在不反复切
终端的情况下快速多开可视化。

## 3D 面板 GPU 渲染（RViz 风） { #gl-panels }

**点云 / 激光 / 位姿 / Marker** 四类面板默认使用 **pyqtgraph + OpenGL**，
走显卡硬件通道，交互体验接近 RViz：

| 操作 | 键位 |
|---|---|
| 环绕视角（orbit）      | 左键拖 |
| **平移视角（pan）**    | **Shift + 左键拖**（触控板友好）／ 中键拖 ／ Ctrl + 左键拖 |
| 缩放                    | 滚轮 |
| 重置到默认方位         | 工具栏 `重置视角` |
| 切换 Z=0 网格 / 原点轴 | 工具栏 `网格` / `原点轴` |

点云面板额外给了 **`点大小` 滑块** 与实时 **`点数` 指示**；超过 20 万点会
自动随机降采到 20 万（并在标签上注明），防止主线程卡顿。

配色：点云按 Z、激光按距离，都走 **Google Turbo** 色图（紫 → 蓝 → 青 →
绿 → 黄 → 红）—— 比 jet 更亮、在深色背景上对比度显著更高。背景色选深蓝黑
而非纯黑，既不刺眼又让暖色点凸显。位姿轴 XYZ=RGB 同 RViz。

性能：百万点量级点云 GPU 流畅刷新；rqt 里可并排打开多个 3D 面板比较。

装依赖：

```bash
pip install --user pyqtgraph PyOpenGL
# 或（Ubuntu 系统包，可选）
sudo apt install python3-pyqtgraph python3-opengl
```

如果 pyqtgraph / PyOpenGL **没装**，rqt 会**自动回退**到 matplotlib 软件 3D
版本（同样能用，但刷新慢、不能流畅交互）。建议装上。

### 验证

仓库自带三个 demo 发布器，专门喂 rqt 的 3D 面板回归：

```bash
# Terminal A —— 27 点立方，自转
python3 examples/python/pointcloud_publisher.py

# Terminal B —— 360 线仿真激光
python3 examples/python/laserscan_publisher.py

# Terminal C —— 真实 PCL 点云文件（任意 .pcd / .ply / .xyz）
python3 examples/python/pcl_publisher.py --file your_cloud.pcd --hz 5

# Terminal D
talos rqt     # 双击 /demo/cloud 与 /demo/scan 即可添加面板
```

### PCL 点云发布工具 { #pcl-publisher }

`examples/python/pcl_publisher.py` 把磁盘上的点云文件当成 PointCloud2
流式发布，用于 rqt 可视化回归、带数据的联调、录制回放：

```bash
# 基本：加载 .pcd 全量点云，5 Hz 发到 /demo/cloud
python3 examples/python/pcl_publisher.py --file bunny.pcd

# 大点云（千万级）降采样 1/10，10 Hz，绕 Z 慢转
python3 examples/python/pcl_publisher.py --file big_scan.pcd \
    --downsample 10 --hz 10 --spin-hz 0.1

# 把 GMM 输出 .ply 重心对齐后上传，一次性发一帧然后退出
python3 examples/python/pcl_publisher.py --file gmm.ply \
    --recenter --once
```

支持格式：`.pcd`（ascii / binary；**binary_compressed 需先 `pcl_convert -format 1`
转成 binary**）、`.ply`（ascii / binary_little / binary_big）、`.xyz` /
`.txt` / `.csv`（空白或逗号分隔，前三列是 XYZ）。

常用参数：

| 参数 | 说明 |
|---|---|
| `--file / -f`     | 点云文件路径 **（必填）** |
| `--topic / -t`    | 默认 `/demo/cloud` |
| `--hz`            | 发布频率（默认 5） |
| `--frame-id`      | 默认 `world` |
| `--downsample N`  | 每 N 点取 1（默认 1 = 全量） |
| `--max-points N`  | 均匀随机抽到最多 N 点（0 = 不限） |
| `--recenter`      | 重心平移到原点 |
| `--spin-hz R`     | 非 0 则绕 Z 轴以 R Hz 自转 |
| `--once`          | 只发一次立即退出 |

无外部依赖 —— 自带 PCD / PLY 头解析器，只用 numpy + talosos。
