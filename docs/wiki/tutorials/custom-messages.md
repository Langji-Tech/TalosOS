# 示例四：自定义消息

TalosOS 提供两种方式定义自定义消息，二者产生**逐字节相同**的 wire 格式，
可以混用：

| 方式 | 用途 |
|---|---|
| `TALOS_MESSAGE_FIELDS` **反射宏** | 单个 C++ 包内一次性类型；几行写完 |
| `.msg` **代码生成** | 要被多个语言 / 多个包复用；跨 C++ / Python |

## 方式 1：反射宏（快速，仅 C++）

任何地方声明一个 struct，最后撒一句 `TALOS_MESSAGE_FIELDS(...)`：

```cpp
#include "talosos/messages.h"
#include "talosos/serialization.h"

struct BatteryTelemetry {
  talos::msgs::Header header;
  float voltage       = 0.f;
  float current       = 0.f;
  uint8_t cell_count  = 0;
  std::vector<float> cell_voltage;

  TALOS_MESSAGE_FIELDS(header, voltage, current, cell_count, cell_voltage)
};
```

宏展开为两个 `talosos_fields()` 访问器；`cdr::Serialize` / `Deserialize`
通过 `std::tie` 自动识别并序列化该 struct。**字段顺序即 wire 顺序** —— 要
跨端匹配必须保持一致。

直接发布 / 订阅：

```cpp
auto pub = node->Advertise<BatteryTelemetry>("battery");
pub.Publish(telem);                 // 与内置类型用法完全一致

node->Subscribe<BatteryTelemetry>("battery",
    [](const BatteryTelemetry& m) {
      TALOS_LOG(INFO) << "V=" << m.voltage;
    });
```

**限制**：只在 C++ 端看得到这个类型；Python 端无法订阅。如果要跨语言
复用，用方式 2。

## 方式 2：`.msg` 代码生成（跨语言）

### 写 `msg/*.msg` 文件

```
# msg/BatteryTelemetry.msg
Header header
float32 voltage
float32 current
uint8  cell_count
float32[] cell_voltage

# 可选常量
uint8 MAX_CELLS=16
```

支持的语法：

| 行样式 | 生成的 C++ |
|---|---|
| `<type> <name>`              | 标量字段 |
| `<type>[N] <name>`           | `std::array<T, N>` 字段 |
| `<type>[] <name>`            | `std::vector<T>` 字段 |
| `<type> <NAME>=<value>`      | `static constexpr` 常量 |
| `Pkg/Msg <name>`             | 引用 `talos::Pkg::Msg` |
| `Header <name>`              | `talos::msgs::Header` 的简写 |

基础类型：`bool / int8 / uint8 / int16 / uint16 / int32 / uint32 / int64 /
uint64 / float32 / float64 / string / time / duration`。

### CMake 接入

```cmake
# find_package(TalosOS) 会自动 include(TalosMessages.cmake)
find_package(TalosOS REQUIRED)

talosos_add_messages(
  NAME battery                        # 生成的 target / 命名空间
  FILES
    msg/BatteryTelemetry.msg
    msg/BatteryStatus.msg
)

add_executable(battery_node src/battery_node.cc)
target_link_libraries(battery_node PRIVATE
    TalosOS::talosos battery_msgs)
```

`talosos_add_messages(NAME battery ...)` 生成三样东西：

1. **C++ 库** `battery_msgs`：头文件在 `talos/battery/*.h`
2. **Python 模块** `talos_battery`：用 `import talos_battery` 加载，对应
   dataclass 与 `TYPE_NAME`
3. **安装产物**：头文件进 `include/`，Python 进 `lib/pythonX.Y/
   site-packages/talos_battery/`，便于下游包 `find_package` / `import`

### 使用生成的类型

=== "C++"

    ```cpp
    #include "talos/battery/BatteryTelemetry.h"

    talos::battery::BatteryTelemetry telem;
    telem.voltage = 12.1f;
    telem.cell_voltage = {3.7f, 3.8f, 3.7f};
    pub.Publish(telem);
    ```

    订阅端同理：

    ```cpp
    node->Subscribe<talos::battery::BatteryTelemetry>(
        "battery", [](const auto& m) { /* ... */ });
    ```

=== "Python"

    ```python
    from talos_battery import BatteryTelemetry
    from talosos.runtime import Node, init

    init()
    node = Node.create("battery_py")
    pub = node.advertise("battery", BatteryTelemetry)

    msg = BatteryTelemetry()
    msg.voltage = 12.1
    msg.cell_voltage = [3.7, 3.8, 3.7]
    pub.publish(msg)

    node.subscribe("battery", BatteryTelemetry,
                     lambda m: print("V =", m.voltage))
    node.spin()
    ```

    生成代码会把 `.msg` 里的 `Header header` 翻成 `header: Header`，
    `float32[] cell_voltage` 翻成 `cell_voltage: list`，常量挂成 `ClassVar`。
    `TYPE_NAME` 自动填成 `BatteryTelemetry` —— 与 C++ 的 `ShortTypeName<T>()`
    对齐，所以 liveliness 里的类型广播跨语言一致。

## 兼容性与字节对齐

TalosOS 的 CDR payload 与 **ROS2 `rclcpp` 生成的消息** 字节级兼容。你可以：

- 拿 ROS2 的 `.msg` 直接粘过来（语法一样）
- 用 `rosbag2` 录的 CDR 包，换成 TalosOS 的 subscriber 直接消费
- TalosOS publisher → ROS2 subscriber 也可（通过 zenoh 的 ROS2 bridge 或
  直接映射 topic）

AddTwoInts 示例中，反射宏版本 与 `.msg` 生成版本序列化后字节完全一致，可
以互相替换。

## 常见陷阱

- **字段顺序错乱**：`TALOS_MESSAGE_FIELDS(a, b)` vs `TALOS_MESSAGE_FIELDS(b, a)`
  ——wire 里的字段顺序 = 列表顺序。换了顺序，旧订阅端马上解不了。
- **float32 vs float64**：`.msg` 里 `float32` ≠ C++ 的 `double`。生成器会
  给 `float32` 写 `float` 类型 + `f32()` 编解码；手写的反射宏里如果把
  `float` 错写成 `double`，字节数对不上、对端全错位。
- **`.msg` 引用另一个包**：要在 `package.yaml` 的 `depends:` 里列出被依赖
  的包，CMake 的 `talosos_add_messages` 才能找到那边的 `.msg`。

## 相关

- [示例一：话题编程](topic.md) —— 把自定义消息用起来
- [功能包与构建](packages.md) —— `talos_msg_gen` 的接入方式
