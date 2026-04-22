# 速查卡 / Cheatsheet

> 一页纸找到 90% 常用 API。左边 C++，右边 Python，行行对应。

## 初始化 & Node

=== "C++"

    ```cpp
    #include "talosos/node.h"
    #include "talosos/logging.h"

    talos::Init(argc, argv);
    auto node = talos::Node::Create("my_node");

    while (talos::Ok()) { /* ... */ }
    ```

=== "Python"

    ```python
    from talosos.runtime import Node, init, ok

    init()
    node = Node.create("my_node")

    while ok():
        ...
    ```

## 发布 / 订阅

=== "C++"

    ```cpp
    #include "talosos/messages.h"

    auto pub = node->Advertise<talos::msgs::String>("chatter");
    talos::msgs::String m; m.data = "hi";
    pub.Publish(m);

    // member-function callback (ROS1 风格):
    auto sub = node->Subscribe("chatter",
        &MyClass::OnMessage, this);

    // lambda:
    auto sub2 = node->Subscribe<talos::msgs::String>(
        "chatter", [](const talos::msgs::String& m) { ... });
    ```

=== "Python"

    ```python
    from talosos.messages import String

    pub = node.advertise("chatter", String)
    pub.publish(String(data="hi"))

    # bound method:
    sub = node.subscribe("chatter", String, self.on_message)
    ```

## 服务

=== "C++"

    ```cpp
    // server
    auto svc = node->AdvertiseService<Req, Resp>(
        "add", &MyClass::OnAdd, this);

    // client
    auto client = node->CreateServiceClient<Req, Resp>("add");
    Req req{3, 4}; Resp resp;
    if (client.Call(req, resp, std::chrono::seconds(1))) {
      TALOS_LOG(INFO) << "sum=" << resp.sum;
    }
    ```

=== "Python"

    ```python
    # server
    svc = node.advertise_service("add", Req, Resp, self.on_add)

    # client
    client = node.create_service_client("add", Req, Resp)
    resp = client.call(Req(a=3, b=4), timeout_ms=1000)
    print(resp.sum)
    ```

## 动作 Action

=== "C++"

    ```cpp
    // server
    auto srv = talos::MakeActionServer<Goal, FB, Result>(
        node, "/fib",
        [](auto& h) {
          while (!h.canceling()) {
            FB fb; fb.seq = ...; h.PublishFeedback(fb);
          }
          Result r; ...
          return std::make_pair(talos::GoalStatus::kSucceeded, r);
        });

    // client
    auto client = talos::MakeActionClient<Goal, FB, Result>(node, "/fib");
    auto handle = client.SendGoal(goal,
        [](const FB& fb){ /* ... */ });
    Result out;  talos::GoalStatus st;
    handle->WaitForResult(out, st);
    ```

=== "Python"

    ```python
    # (action 的 Python 绑定与 C++ 结构一致,
    #  具体 API 参见 tutorials/action.md)
    ```

## 自定义消息

=== "反射宏 (最快)"

    ```cpp
    #include "talosos/serialization.h"
    #include "talosos/messages.h"

    struct Telemetry {
      talos::msgs::Header header;
      float voltage = 0.f;
      std::vector<float> cells;
      TALOS_MESSAGE_FIELDS(header, voltage, cells)
    };
    ```

=== "`.msg` 代码生成 (ROS 风格)"

    ```
    # msg/Telemetry.msg
    Header header
    float32 voltage
    float32[] cells
    ```

    ```cmake
    find_package(TalosOS REQUIRED)
    talosos_add_messages(
      NAME battery
      FILES msg/Telemetry.msg
    )
    target_link_libraries(my_node PRIVATE battery_msgs)
    ```

    ```cpp
    #include "talos/battery/Telemetry.h"
    talos::battery::Telemetry telem;
    ```

## OpenCV cv_bridge

```cpp
#include "talosos/adapters/opencv.h"

cv::Mat bgr = cv::imread("x.png", cv::IMREAD_COLOR);

// raw
auto raw  = talos::adapters::ToImageMessage(bgr, header);      // encoding 自动推导
auto mat  = talos::adapters::ToCvMat(raw);                     // 零拷贝视图

// compressed
auto jpg  = talos::adapters::ToCompressedImageMessage(bgr, "jpg");
auto mat2 = talos::adapters::ToCvMat(jpg);                      // cv::imdecode
```

## 日志

| 风格 | 示例 |
| --- | --- |
| glog / `<<` | `TALOS_LOG(INFO) << "n=" << n;` |
| ROS1 STREAM | `TALOS_INFO_STREAM("n=" << n);` |
| printf | `TALOS_INFO("n=%d", n);` |

等级：`DEBUG / INFO / WARN / ERROR / FATAL`。关闭时宏编译成 `(void)0`。

## 话题名规则

| 代码 | zenoh key | 含义 |
| --- | --- | --- |
| `"/chat"` | `chat` | 绝对 |
| `"chat"`  | `<ns/name>/chat` | 相对（命名空间下）|
| `"~/chat"` | `<ns/name>/chat` | 私有别名 |

CLI 列出 / 订阅时**总是带前导 `/`**（与 ROS 一致）。

## CLI 速查

| 命令 | 作用 |
| --- | --- |
| `talos pkg create <name> [--with-node]` | 新建包（自动 init workspace）|
| `talos pkg list [--verbose] [--json]` | 枚举包 |
| `talos build [pkgs...] [-j N]` | 构建 + install 到 `<ws>/install` |
| `talos run <pkg> <exe> [args...]` | 执行已装的可执行 |
| `talos topic list / echo / hz / bw / pub / info` | 话题工具 |
| `talos service list / call / info` | 服务工具 |
| `talos launch <file>` | 跑 YAML 多节点图 |
| `talos plot <topic> --type T --field a.b` | matplotlib 实时曲线 |
| `talos viz  <topic> --type T` | 图像 / 扫描 / 点云 / 标记渲染 |
| `talos rqt` | PyQt5 主壳 |

## 节点网络配置

=== "C++"

    ```cpp
    talos::NodeOptions opts;
    opts.mode = "peer";                       // peer | client | router
    opts.listen = {"tcp/0.0.0.0:7447"};
    opts.connect = {"tcp/192.168.1.10:7447"};
    opts.multicast = false;
    auto node = talos::Node::Create("n", opts);
    ```

=== "Python"

    ```python
    node = Node.create("n",
                       mode="peer",
                       listen=["tcp/0.0.0.0:7447"],
                       connect=["tcp/192.168.1.10:7447"],
                       multicast=False)
    ```

=== "CLI"

    ```bash
    talos topic pub /chat --utf8 "hi" \
         --mode peer --listen tcp/0.0.0.0:7447 --no-multicast
    ```
