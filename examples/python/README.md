# Python examples

Python mirrors of the C++ examples under `examples/cpp/`. They exercise the
pybind11 runtime in `talosos.runtime` and the Python CDR codec in
`talosos.messages`, producing wire payloads byte-identical to the C++ side.

## Prerequisites

```bash
source /opt/talosos/setup.bash      # (or your local install prefix)
python3 -c "from talosos.runtime import Node"   # should import cleanly
```

## pub / sub

```bash
# Terminal A
python3 examples/python/listener.py

# Terminal B
python3 examples/python/talker.py
```

The listener can also consume the **C++** talker transparently (and vice
versa):

```bash
# Terminal A
python3 examples/python/listener.py

# Terminal B
talos run some_cpp_pkg talker         # or use the built-in demo
```

## Service

```bash
# Terminal A
python3 examples/python/add_two_ints_server.py

# Terminal B
python3 examples/python/add_two_ints_client.py 7 35
# -> 7 + 35 = 42
```

These request/response types are wire-compatible with the C++
`examples/cpp/add_two_ints` binaries — you can pair Python client with C++
server and vice versa.

## Image pub/sub

Uses the same PNG the C++ demo does.

```bash
# Terminal A — subscriber (saves up to 3 frames to /tmp/py_image_demo_frame_*.png)
python3 examples/python/image_subscriber.py 3

# Terminal B — publisher at 2 Hz
python3 examples/python/image_publisher.py /home/ubuntu24/Software/TalosOS/image.png 2.0
```

Verify byte-level round-trip:

```bash
sha256sum /home/ubuntu24/Software/TalosOS/image.png /tmp/py_image_demo_frame_0.png
# hashes must match
```

## rqt 可视化测试源

两个现成的发布者，专门喂 `talos rqt` 做 PointCloud2 / LaserScan 面板回归：

```bash
# Terminal A — 27 点 3×3×3 立方，绕 Z 慢转
python3 examples/python/pointcloud_publisher.py

# Terminal B — 360 线仿真激光，含旋转近物 + 静态远物
python3 examples/python/laserscan_publisher.py

# Terminal C
talos rqt          # 自动发现 /demo/cloud 与 /demo/scan，点 + 添加面板
```

两个脚本都支持 `--topic / --hz / --frame-id` 覆盖；cube 额外支持 `--side`
与 `--spin-hz`，scan 额外支持 `--rays`。

对真实 PCL 数据，用 `pcl_publisher.py`：

```bash
python3 examples/python/pcl_publisher.py --file bunny.pcd           # .pcd
python3 examples/python/pcl_publisher.py --file model.ply --hz 10   # .ply
python3 examples/python/pcl_publisher.py --file data.xyz --recenter \
    --downsample 4 --spin-hz 0.1                                     # .xyz
```

格式自动按后缀识别（`.pcd / .ply / .xyz / .txt / .csv`），`--downsample` /
`--max-points` / `--recenter` / `--spin-hz` / `--once` 可按需组合。无外部
依赖，只用 numpy + talosos。

### OccupancyGrid + Octomap（地图类）

```bash
# 随机 2D 占用栅格（100×100，分辨率 0.1m，有墙）
python3 examples/python/random_gridmap_publisher.py --walls --animate

# 随机八叉树（深度 4，根边长 8m，每帧重建）
python3 examples/python/random_octomap_publisher.py --max-depth 4 --rebuild

# 另起终端
talos viz
# 双击 /map      → XOY 平面贴图（RViz Map 风）
# 双击 /octomap  → 3D 彩色立方体体素叠加在同一场景里
```

Octomap 的 `data` 载荷格式：`id="talos_voxels_v1"`，连续
`float32 {x,y,z,size}`，每体素 16 字节；发布器 / viz 双方各自实现。
真正的 `octomap_msgs/Octomap` 二叉树解码暂未实现（`id` 不匹配时 viz
会安全跳过而不崩）。

## Cross-language compatibility

| Run on side A           | Run on side B                    | Works |
| ----------------------- | -------------------------------- | ----- |
| `talker.py` (Python)    | `listener.py` (Python)           | ✅    |
| `talker.py` (Python)    | `listener` (C++)                 | ✅    |
| C++ image_publisher     | `image_subscriber.py`            | ✅    |
| `image_publisher.py`    | C++ image_subscriber             | ✅    |

All exchanged payloads are little-endian CDR with a 4-byte encapsulation
header, so the usual ROS2 bag / Foxglove tooling can consume them too.
