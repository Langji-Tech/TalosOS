# 消息类型参考

`include/talosos/messages.h` 提供了 ROS2 兼容的消息子集。所有 wire 格式采
用小端 CDR + 4 字节封装头，与 `rclcpp` 生成的消息格式完全一致——payload
可以直接喂给 `ros2 bag`、Foxglove 或 Zenoh bridge。

## 伞形头文件

```cpp
#include "talosos/messages.h"   // 引入下面所有内容
```

大型 TU 中为了控制编译时间，可以按需引入子头：

```cpp
#include "talosos/msgs/geometry_msgs.h"
#include "talosos/msgs/sensor_msgs.h"
```

## std_msgs

`Header`、`Empty`、`String`、`Bool`、`Byte`、`Char`、`Int8..Int64`、
`UInt8..UInt64`、`Float32`、`Float64`、`ColorRGBA`、
`MultiArrayDimension`、`MultiArrayLayout`，以及 11 种 `*MultiArray`
变体。

## geometry_msgs

- 基本类型：`Vector3`、`Point`、`Point32`、`Quaternion`、`Pose2D`、
  `Pose`、`Twist`、`Accel`、`Wrench`、`Inertia`、`Polygon`、`Transform`。
- 带时间戳：上述全部的 `*Stamped` 变体。
- 带协方差：`PoseWithCovariance[Stamped]`、
  `TwistWithCovariance[Stamped]`、`AccelWithCovariance[Stamped]`。

## sensor_msgs

`RegionOfInterest`、`Imu`、`Image`、`CompressedImage`、`CameraInfo`、
`LaserScan`、`PointField`（含类型常量）、`PointCloud2`、
`PointCloud`（legacy）、`ChannelFloat32`、`JointState`、`NavSatStatus`、
`NavSatFix`、`Range`、`Temperature`、`RelativeHumidity`、
`FluidPressure`、`Illuminance`、`MagneticField`、`TimeReference`、
`BatteryState`、`Joy`。

## nav_msgs

`Path`、`Odometry`、`MapMetaData`、`OccupancyGrid`、`GridCells`。

## tf2_msgs

`TFMessage`。

## visualization_msgs

`Marker`（12 种 type 常量 + 4 种 action）、`MarkerArray`、
`ImageMarker`、`MenuEntry`。

## pcl_msgs

`PointIndices`、`ModelCoefficients`、`Vertices`、`PolygonMesh`。

## octomap_msgs

`Octomap`、`OctomapWithPose`。

## 序列化助手

```cpp
std::vector<uint8_t> bytes = talos::cdr::Serialize(my_msg);
MyMsg decoded = talos::cdr::Deserialize<MyMsg>(bytes.data(), bytes.size());
```

自定义类型通过 `TALOS_MESSAGE_FIELDS(...)` 接入（见
[自定义消息](../tutorials/custom-messages.md)）；手写类型可以提供
`Write(cdr::Writer&, const T&)` / `Read(cdr::Reader&, T&)` 自由函数，
依靠 ADL 查找。

## Python 解码

`talosos.messages` 以 dataclass 形式镜像了常用子集，每种类型提供 `.read(CdrReader)`
类方法；`talosos.runtime` 把它们接入 `Node.advertise/subscribe/advertise_service`，
从而让 Python 节点与 C++ 运行时交换**同一份 CDR payload**。
