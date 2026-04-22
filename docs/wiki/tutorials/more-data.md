# 示例七：其他常见数据类型传输

前面几章覆盖了 String / Int64 / Image / PointCloud2 等"主线"消息；本章
把剩下常见的**传感器 / 状态 / 可视化**消息类型挑一遍，每种配一段最短
发布 + 订阅代码。用哪种消息做哪件事，本章一览。

| 本章涵盖 | 典型用途 |
|---|---|
| [`Imu`](#imu)                               | 惯导 / 姿态 |
| [`LaserScan`](#laserscan)                   | 2D 激光雷达 |
| [`PoseStamped` / `TransformStamped` / `TFMessage`](#tf) | 位姿 / 坐标系变换 |
| [`Marker` / `MarkerArray`](#marker)         | 调试性 3D 可视化对象 |
| [`OccupancyGrid`](#occupancygrid)           | 2D 栅格地图（SLAM 输出） |
| [`Octomap`](#octomap)                       | 3D 八叉树地图 |

所有这些类型都是**C++ / Python 双端可发可收**。前面四章讲过的 pub/sub
模板直接套用，本章只列类型专属的字段填写 + 可视化命令。

## <span id="imu"></span>Imu — 惯导

=== "C++"

    ```cpp
    #include "talosos/messages.h"
    #include "talosos/node.h"

    auto pub = node->Advertise<talos::msgs::Imu>("/imu");

    talos::msgs::Imu imu;
    imu.header.frame_id = "imu_link";
    imu.header.stamp    = talos::Time::Now();
    imu.orientation     = { .x = 0, .y = 0, .z = 0, .w = 1 };
    imu.angular_velocity    = { .x = 0.01, .y = 0.0, .z = 0.0 };
    imu.linear_acceleration = { .x = 0.0,  .y = 0.0, .z = 9.81 };
    // 9 个协方差填 0 表示"未知"
    pub.Publish(imu);
    ```

=== "Python"

    ```python
    from talosos.messages import Imu, Quaternion, Vector3, Header, Time as TMsg

    pub = node.advertise("/imu", Imu)
    msg = Imu(
        header=Header(frame_id="imu_link"),
        orientation=Quaternion(w=1.0),
        angular_velocity=Vector3(x=0.01),
        linear_acceleration=Vector3(z=9.81),
    )
    pub.publish(msg)
    ```

可视化：`talos viz --all-types`，IMU panel 会画三路加速度 + 三路角速度
+ orientation.w 的时序曲线（matplotlib）。

## <span id="laserscan"></span>LaserScan — 2D 激光

=== "C++"

    ```cpp
    talos::msgs::LaserScan scan;
    scan.header.frame_id = "laser";
    scan.angle_min = -M_PI;
    scan.angle_max =  M_PI;
    scan.angle_increment = 2 * M_PI / 360.0f;
    scan.time_increment = 0.0f;
    scan.scan_time = 0.1f;
    scan.range_min = 0.1f;
    scan.range_max = 10.0f;
    scan.ranges.resize(360, 5.0f);       // 全部 5m 远
    scan.intensities.resize(0);
    pub.Publish(scan);
    ```

=== "Python"

    ```python
    import math
    from talosos.messages import LaserScan, Header

    scan = LaserScan(
        header=Header(frame_id="laser"),
        angle_min=-math.pi, angle_max=math.pi,
        angle_increment=2 * math.pi / 360,
        range_min=0.1, range_max=10.0,
        ranges=[5.0] * 360,
    )
    pub.publish(scan)
    ```

可视化：`talos viz` dashboard 双击 `/scan` —— 射线扇形 + 端点按距离 turbo
上色。完整 demo：`examples/python/laserscan_publisher.py`。

## <span id="tf"></span>PoseStamped / TF

坐标系变换三类：**`PoseStamped`**（单个位姿）/ **`TransformStamped`**（带
父子 frame 的变换）/ **`TFMessage`**（一组 TransformStamped，是 ROS tf tree
的载体）。

=== "C++"

    ```cpp
    // --- 发布机器人当前位姿 ---
    auto pose_pub = node->Advertise<talos::msgs::PoseStamped>("/robot/pose");
    talos::msgs::PoseStamped ps;
    ps.header.frame_id = "odom";
    ps.pose.position    = { 1.0, 2.0, 0.0 };
    ps.pose.orientation = { .w = 1.0 };
    pose_pub.Publish(ps);

    // --- 发布 TF 树 ---
    auto tf_pub = node->Advertise<talos::msgs::TFMessage>("/tf");
    talos::msgs::TransformStamped t;
    t.header.frame_id = "odom";
    t.child_frame_id  = "base_link";
    t.transform.translation = { 1.0, 2.0, 0.0 };
    t.transform.rotation    = { .w = 1.0 };
    talos::msgs::TFMessage tfm;
    tfm.transforms.push_back(t);
    tf_pub.Publish(tfm);
    ```

=== "Python"

    ```python
    from talosos.messages import (PoseStamped, Pose, Point, Quaternion,
                                    TransformStamped, TFMessage,
                                    Transform, Vector3, Header)

    pose_pub = node.advertise("/robot/pose", PoseStamped)
    pose_pub.publish(PoseStamped(
        header=Header(frame_id="odom"),
        pose=Pose(position=Point(x=1, y=2), orientation=Quaternion(w=1))))

    tf_pub = node.advertise("/tf", TFMessage)
    tf_pub.publish(TFMessage(transforms=[
        TransformStamped(header=Header(frame_id="odom"),
                          child_frame_id="base_link",
                          transform=Transform(
                              translation=Vector3(x=1, y=2),
                              rotation=Quaternion(w=1))),
    ]))
    ```

可视化：viz dashboard 里双击 `/robot/pose` → 轨迹折线 + XYZ=RGB 三段姿态轴；
`talos viz /tf --type TFMessage` → 命令行打印 tf tree。

## <span id="marker"></span>Marker / MarkerArray — 调试几何体

用来在 3D 场景里画线段 / 点 / 立方体等调试标记。`Marker.type` 取值：
`ARROW=0, CUBE=1, SPHERE=2, CYLINDER=3, LINE_STRIP=4, LINE_LIST=5,
CUBE_LIST=6, SPHERE_LIST=7, POINTS=8`。

=== "C++"

    ```cpp
    auto pub = node->Advertise<talos::msgs::MarkerArray>("/markers");

    // 画一条红色折线（LINE_STRIP）
    talos::msgs::Marker line;
    line.header.frame_id = "world";
    line.ns = "demo"; line.id = 0;
    line.type = talos::msgs::Marker::LINE_STRIP;
    line.scale.x = 0.05;                       // 线宽
    line.color = { .r = 1, .g = 0.2, .b = 0.2, .a = 1 };
    line.points.push_back({0, 0, 0});
    line.points.push_back({1, 1, 0});
    line.points.push_back({2, 0, 1});

    talos::msgs::MarkerArray arr;
    arr.markers.push_back(line);
    pub.Publish(arr);
    ```

=== "Python"

    ```python
    from talosos.messages import (Marker, MarkerArray, Header,
                                    ColorRGBA, Vector3, Point)

    pub = node.advertise("/markers", MarkerArray)
    line = Marker(
        header=Header(frame_id="world"),
        ns="demo", id=0, type=Marker.LINE_STRIP,
        scale=Vector3(x=0.05),
        color=ColorRGBA(r=1, g=0.2, b=0.2, a=1),
        points=[Point(x=0,y=0), Point(x=1,y=1), Point(x=2,y=0,z=1)],
    )
    pub.publish(MarkerArray(markers=[line]))
    ```

可视化：viz dashboard 双击 `/markers`，自动识别 MarkerArray 图层，按
`type` 分别绘制。

## <span id="occupancygrid"></span>OccupancyGrid — 2D 栅格地图

2D 栅格地图，`data` 是 `int8[width*height]`：`-1`=未知、`0`=自由、
`1..100`=占据概率（%）。

=== "C++"

    ```cpp
    auto pub = node->Advertise<talos::msgs::OccupancyGrid>("/map");

    talos::msgs::OccupancyGrid grid;
    grid.header.frame_id = "map";
    grid.info.resolution = 0.05;    // 5cm / cell
    grid.info.width  = 200;         // 10m
    grid.info.height = 200;
    grid.info.origin.position = { -5.0, -5.0, 0.0 };  // 世界坐标
    grid.data.assign(200 * 200, 0);                   // 全自由
    // 画一圈墙（概率 100%）
    for (uint32_t i = 0; i < 200; ++i) {
      grid.data[i] = 100;                       // 顶
      grid.data[199 * 200 + i] = 100;           // 底
      grid.data[i * 200] = 100;                 // 左
      grid.data[i * 200 + 199] = 100;           // 右
    }
    pub.Publish(grid);
    ```

=== "Python"

    ```python
    import numpy as np
    from talosos.messages import (OccupancyGrid, MapMetaData, Header,
                                    Pose, Point)

    pub = node.advertise("/map", OccupancyGrid)
    grid = np.zeros((200, 200), dtype=np.int8)
    grid[0, :] = 100; grid[-1, :] = 100
    grid[:, 0] = 100; grid[:, -1] = 100
    pub.publish(OccupancyGrid(
        header=Header(frame_id="map"),
        info=MapMetaData(resolution=0.05, width=200, height=200,
                          origin=Pose(position=Point(x=-5, y=-5))),
        data=grid.tobytes()))
    ```

可视化：viz dashboard 里双击 `/map` → 在 XOY 平面画成纹理贴图
（RViz Map 风）：未知 = 深蓝灰半透、自由 = 近白、占据 = 深灰按概率渐变。

完整随机地图 demo：`examples/python/random_gridmap_publisher.py`。

## <span id="octomap"></span>Octomap — 3D 八叉树地图

`octomap_msgs/Octomap` 的 `data` 字段在真实 ROS 里是 OctoMap 库的二叉树
编码。TalosOS viz 内建识别 **demo 格式** `id="talos_voxels_v1"` —— `data`
是连续的 `float32 {x, y, z, size}` 每体素 16 字节。`OctomapWithPose`
多一个 `Pose origin` 字段做整体平移 / 旋转。

=== "C++"

    ```cpp
    auto pub = node->Advertise<talos::msgs::Octomap>("/octomap");

    std::vector<float> voxels;           // x0,y0,z0,s0, x1,y1,z1,s1, ...
    for (int i = 0; i < 50; ++i) {
      voxels.push_back((i % 5) * 0.5f);       // x
      voxels.push_back((i / 5) * 0.5f);       // y
      voxels.push_back(0.25f);                // z
      voxels.push_back(0.5f);                 // size
    }

    talos::msgs::Octomap oc;
    oc.header.frame_id = "map";
    oc.id         = "talos_voxels_v1";
    oc.resolution = 0.5;
    oc.binary     = false;
    oc.data.assign(
        reinterpret_cast<const uint8_t*>(voxels.data()),
        reinterpret_cast<const uint8_t*>(voxels.data()) + voxels.size() * 4);
    pub.Publish(oc);
    ```

=== "Python"

    ```python
    import numpy as np
    from talosos.messages import Octomap, Header

    pub = node.advertise("/octomap", Octomap)
    voxels = np.array([(i%5*0.5, i//5*0.5, 0.25, 0.5) for i in range(50)],
                        dtype=np.float32)
    pub.publish(Octomap(
        header=Header(frame_id="map"),
        id="talos_voxels_v1", resolution=0.5, binary=False,
        data=voxels.tobytes()))
    ```

可视化：viz dashboard 里双击 `/octomap` → 每体素一个彩色立方体
（`GLMeshItem` 批量），按 Z 上 turbo、带边缘线。

完整随机八叉树 demo：`examples/python/random_octomap_publisher.py`。

## 类型一览与选型

| 你有 | 用什么 |
|---|---|
| 标量传感器读数（电压、温度） | `Float32` / `Float64` |
| 数字 / 布尔标志 | `Int32` / `Bool` |
| 文本日志 / 命令 | `String` |
| 相机原始 / 压缩帧 | [`Image` / `CompressedImage`](image-transport.md) |
| 深度 / 激光 / 稠密点云 | [`PointCloud2`](pointcloud-io.md) |
| 2D 激光 | `LaserScan`（上面） |
| 姿态 / TF | `PoseStamped` / `TFMessage`（上面） |
| IMU 融合数据 | `Imu`（上面） |
| 调试几何体 | `MarkerArray`（上面） |
| 2D 栅格地图 | `OccupancyGrid`（上面） |
| 3D 地图 | `Octomap`（上面） |

要**自己定义**新消息 → 看 [示例四：自定义消息](custom-messages.md)。

## 相关

- [rqt / viz 工具箱](rqt.md) —— 所有这些消息的交互式可视化
- [示例一：话题编程](topic.md) —— pub/sub 基本用法
- [示例四：自定义消息](custom-messages.md) —— 要定义更多类型
