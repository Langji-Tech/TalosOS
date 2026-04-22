# 示例六：点云传输

`sensor_msgs/PointCloud2` 是 TalosOS 里最通用的 3D 数据载体 ——
激光雷达、深度相机重建、SLAM 建图、物体检测输出都用它。本章涵盖：基础
pub/sub、`fields` 约定（x/y/z/intensity）、与 `.pcd / .ply` 文件的双向
I/O、以及与 PCL / CloudCompare / Open3D 等外部工具的互通。

## PointCloud2 基础收发

### 字段约定

PointCloud2 用**动态 `fields` 列表**描述每个点的结构。最常见的布局：

| fields                            | point_step | 语义 |
|---|---|---|
| `x, y, z`                         | 12 | 纯坐标（本教程默认） |
| `x, y, z, intensity`              | 16 | 激光雷达 |
| `x, y, z, rgb`                    | 16 | 彩色点云（rgb 打包成 float32） |
| `x, y, z, normal_x, normal_y, normal_z` | 24 | 带法向量 |

每个字段 4 字节 float32。发布时设置 `is_dense = true`（无 NaN）可以让
下游跳过有效性检查。

### 发布端

=== "C++"

    ```cpp
    #include <vector>
    #include <chrono>

    #include "talosos/messages.h"
    #include "talosos/node.h"

    int main(int argc, char** argv) {
      talos::Init(argc, argv);
      auto node = talos::Node::Create("cloud_pub");
      auto pub = node->Advertise<talos::msgs::PointCloud2>("/demo/cloud");

      // 生成 3x3x3 = 27 个点的立方
      std::vector<float> data;
      for (int x = -1; x <= 1; ++x)
        for (int y = -1; y <= 1; ++y)
          for (int z = -1; z <= 1; ++z) {
            data.push_back(x * 0.5f);
            data.push_back(y * 0.5f);
            data.push_back(z * 0.5f);
          }

      talos::msgs::PointCloud2 msg;
      msg.header.frame_id = "world";
      msg.height = 1;
      msg.width  = 27;
      msg.fields = {
        {"x", 0, talos::msgs::PointField::FLOAT32, 1},
        {"y", 4, talos::msgs::PointField::FLOAT32, 1},
        {"z", 8, talos::msgs::PointField::FLOAT32, 1},
      };
      msg.is_bigendian = false;
      msg.point_step   = 12;
      msg.row_step     = 12 * 27;
      msg.is_dense     = true;
      msg.data.assign(reinterpret_cast<const uint8_t*>(data.data()),
                       reinterpret_cast<const uint8_t*>(data.data()) + data.size() * 4);

      while (talos::Ok()) {
        msg.header.stamp = talos::Time::Now();
        pub.Publish(msg);
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
      }
    }
    ```

=== "Python"

    ```python
    import math, time
    import numpy as np

    from talosos.messages import Header, PointCloud2, PointField, Time as TMsg
    from talosos.runtime import Node, init, ok

    init()
    node = Node.create("cloud_pub_py")
    pub = node.advertise("/demo/cloud", PointCloud2)

    # 27 点立方
    axis = np.linspace(-0.5, 0.5, 3, dtype=np.float32)
    pts = np.array([(x, y, z) for x in axis for y in axis for z in axis],
                     dtype=np.float32)

    while ok():
        now = time.time_ns()
        msg = PointCloud2(
            header=Header(frame_id="world",
                            stamp=TMsg(sec=now // 1_000_000_000,
                                         nanosec=now % 1_000_000_000)),
            height=1, width=len(pts),
            fields=[
                PointField(name="x", offset=0, datatype=PointField.FLOAT32, count=1),
                PointField(name="y", offset=4, datatype=PointField.FLOAT32, count=1),
                PointField(name="z", offset=8, datatype=PointField.FLOAT32, count=1),
            ],
            is_bigendian=False,
            point_step=12, row_step=12 * len(pts),
            data=pts.tobytes(),
            is_dense=True)
        pub.publish(msg)
        time.sleep(0.2)
    ```

### 订阅端 — 解析 xyz

=== "C++"

    ```cpp
    node->Subscribe<talos::msgs::PointCloud2>("/demo/cloud",
        [](const talos::msgs::PointCloud2& msg) {
          const size_t n = msg.data.size() / msg.point_step;
          // 简单：假设布局是 x(0) y(4) z(8) 且 point_step=12
          const float* p = reinterpret_cast<const float*>(msg.data.data());
          float xmin = p[0];
          for (size_t i = 0; i < n; ++i) {
            const float x = p[i * 3 + 0];
            if (x < xmin) xmin = x;
          }
          TALOS_INFO("got %zu pts, xmin=%.3f", n, xmin);
        });
    ```

    更严谨的写法先查 `fields`：

    ```cpp
    // Find x field offset dynamically
    int off_x = -1, off_y = -1, off_z = -1;
    for (auto& f : msg.fields) {
      if (f.name == "x") off_x = f.offset;
      if (f.name == "y") off_y = f.offset;
      if (f.name == "z") off_z = f.offset;
    }
    if (off_x < 0) return;  // 这个 cloud 没有 xyz
    for (size_t i = 0; i < n; ++i) {
      const uint8_t* base = msg.data.data() + i * msg.point_step;
      float x = *reinterpret_cast<const float*>(base + off_x);
      float y = *reinterpret_cast<const float*>(base + off_y);
      float z = *reinterpret_cast<const float*>(base + off_z);
      // ...
    }
    ```

=== "Python"

    ```python
    import numpy as np
    from talosos.messages import PointCloud2

    def on_cloud(msg: PointCloud2) -> None:
        fields = {f.name: f for f in msg.fields}
        if not all(k in fields for k in ("x", "y", "z")):
            return
        n = len(msg.data) // msg.point_step
        buf = np.frombuffer(bytes(msg.data), dtype=np.uint8).reshape(n, msg.point_step)
        def col(name):
            off = fields[name].offset
            return np.frombuffer(buf[:, off:off+4].tobytes(), dtype=np.float32)
        xyz = np.column_stack([col("x"), col("y"), col("z")])
        xyz = xyz[np.isfinite(xyz).all(axis=1)]
        print(f"got {len(xyz)} pts, bbox {xyz.min(0)} .. {xyz.max(0)}")

    node.subscribe("/demo/cloud", PointCloud2, on_cloud)
    node.spin()
    ```

    仓库里已经封装好：`examples/python/pcl_saver.py` 的
    `pointcloud2_to_xyz()` 就是这段代码的生产版。

## PCL / PLY 文件 ↔ 话题流

TalosOS 自带两个互为反向的 Python 工具，让磁盘上的点云文件和 `PointCloud2`
话题流相互流动：

| 方向 | 工具 | 作用 |
|---|---|---|
| 磁盘 → 话题 | `examples/python/pcl_publisher.py` | 读 `.pcd / .ply / .xyz`，按指定频率发布 `PointCloud2` |
| 话题 → 磁盘 | `examples/python/pcl_saver.py`    | 订阅 `PointCloud2`，保存为 `.pcd / .ply` |

两边的解析器 / 序列化器是在仓库里用纯 numpy 实现的，**无外部依赖**
（不需要 pcl-tools / open3d / plyfile）。两边彼此字节级回环：saver 写出的
文件再丢给 publisher 重新发布，数据与原始点一字不差。

## 磁盘 → 话题（发布）

```bash
# 基本：加载 .pcd，5 Hz 发到 /demo/cloud
python3 examples/python/pcl_publisher.py --file bunny.pcd

# 大点云降采样 + 慢转，方便在 viz 里观察
python3 examples/python/pcl_publisher.py --file big_scan.pcd \
    --downsample 10 --hz 10 --spin-hz 0.1

# 把 .ply 重心平移到原点，只发一次然后退出
python3 examples/python/pcl_publisher.py --file model.ply \
    --recenter --once
```

支持格式：

| 后缀 | 解析细节 |
|---|---|
| `.pcd` | ROS / PCL 原生。支持 `DATA ascii` 与 `DATA binary`；**`binary_compressed` 不支持**（请先 `pcl_convert -format 1` 转成 `binary`）|
| `.ply` | `format ascii 1.0`、`binary_little_endian 1.0`、`binary_big_endian 1.0` 都支持；只取 x / y / z 三列 |
| `.xyz` / `.txt` / `.csv` | 空白或逗号分隔，每行前三列视为 xyz；`#` 开头的行当注释跳过 |

常用参数（完整清单见 `--help`）：

| 参数 | 说明 |
|---|---|
| `--file / -f`     | 输入文件路径 **（必填）** |
| `--topic / -t`    | 默认 `/demo/cloud` |
| `--frame-id`      | 默认 `world` |
| `--hz`            | 发布频率（默认 5） |
| `--downsample N`  | 每 N 点取 1（默认 1 = 全量） |
| `--max-points N`  | 均匀随机抽到最多 N 点 |
| `--recenter`      | 重心平移到原点 |
| `--spin-hz R`     | 绕 Z 轴以 R Hz 自转 |
| `--once`          | 只发一次立即退出 |

## 话题 → 磁盘（订阅并保存）

```bash
# 存第一帧到文件就退出（默认 --once）
python3 examples/python/pcl_saver.py --topic /demo/cloud --out snap.pcd

# 存连续 20 帧：snap_000.pcd snap_001.pcd … snap_019.pcd
python3 examples/python/pcl_saver.py -t /demo/cloud -o snap.pcd --count 20

# 持续覆写同一文件 —— live.ply 始终是最新帧，适合外部工具轮询
python3 examples/python/pcl_saver.py -t /demo/cloud -o live.ply --continuous

# ASCII 模式（便于 diff / 文本检视；默认 binary，体积小 5-7 倍）
python3 examples/python/pcl_saver.py -t /demo/cloud -o text.pcd --ascii
```

输出格式由 `--out` 的后缀决定（`.pcd` 或 `.ply`）；写盘模式由
`--ascii` 开关决定（默认 binary）：

| 格式 / 模式 | 头部 |
|---|---|
| PCD binary | `FIELDS x y z` + `SIZE 4 4 4` + `TYPE F F F` + `DATA binary` |
| PCD ascii  | 同上 + `DATA ascii`，一行一个点 |
| PLY binary | `format binary_little_endian 1.0` + 三个 `property float` |
| PLY ascii  | `format ascii 1.0` + 三个 `property float` |

## 一端到另一端的闭环测试

把两个工具串起来可以做**零配置**的回环测试，验证序列化路径 OK：

```bash
# 终端 1：从 bunny.pcd 一次性发一帧
python3 examples/python/pcl_publisher.py --file bunny.pcd --once --hz 0.5 &

# 终端 2：订阅存盘
python3 examples/python/pcl_saver.py -t /demo/cloud -o out.ply

# 终端 3：核对 —— 点数、范围应该与原文件一致
python3 -c "
import sys; sys.path.insert(0, 'examples/python')
from pcl_publisher import load_cloud
import numpy as np
a = load_cloud(__import__('pathlib').Path('bunny.pcd'))
b = load_cloud(__import__('pathlib').Path('out.ply'))
print('orig', a.shape, 'recv', b.shape)
print('bbox eq:', np.allclose(a.min(0), b.min(0)) and np.allclose(a.max(0), b.max(0)))
"
```

## 与 RViz / CloudCompare 等工具互通

写出的 `.pcd` / `.ply` 是**标准格式**，直接可被以下工具打开：

- `pcl_viewer snap.pcd`（PCL tools）
- `CloudCompare snap.ply`（图形界面点云编辑器）
- Blender → `File → Import → Stanford PLY`
- Open3D：`o3d.io.read_point_cloud("snap.ply")`
- MeshLab、Autodesk Recap 等

反向也成立：任何工具导出的 `.pcd` / `.ply` 都能直接喂给 `pcl_publisher.py`。

## 实现说明

两个工具都住在 `examples/python/`，便于直接改。想扩展字段（例如带 RGB、
normal、intensity）只需：

1. 改 `pcl_publisher.py` 的 `load_pcd` / `load_ply` 把相应列读进来
2. 改 `pcl_saver.py` 的 `pointcloud2_to_xyz` 改成同时提取 RGB / intensity
3. 改 `write_pcd` / `write_ply` 头部 + 数据块加入多字段

PointCloud2 `fields` 数组已能描述任意 FIELDS，核心的 CDR 序列化代码
（`runtime._w_point_cloud2` 和 `messages.PointCloud2.read`）不需要动。

## 相关

- [示例五 · 图像传输 / cv_bridge](image-transport.md) —— 相机流用 Image 而非 PointCloud2
- [图像延时 / 丢帧基准](image-bench.md) —— 传输性能测量
- [rqt / viz 工具箱](rqt.md#gl-panels) —— 3D 点云可视化面板
