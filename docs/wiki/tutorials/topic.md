# 示例一：话题编程

话题 (topic) 是 TalosOS 最常用的通信机制 —— publisher 以某个名字发布消息，
任意数量的 subscriber 收取。本章覆盖：最小 pub/sub、类风格节点、三种回调
绑定写法、命名空间与话题解析、跨语言互通。

!!! note "先决条件"

    已完成 [功能包与构建](packages.md)；本章代码假定你在一个 TalosOS 工作
    空间下、已经 `talos pkg create hello --with-node` 创建了骨架。

## 最小 publisher / subscriber

=== "C++"

    publisher，`src/hello_node.cc`：

    ```cpp
    #include <chrono>
    #include <thread>

    #include "talosos/logging.h"
    #include "talosos/messages.h"
    #include "talosos/node.h"

    int main(int argc, char** argv) {
      talos::Init(argc, argv);
      auto node = talos::Node::Create("hello_node");
      auto pub = node->Advertise<talos::msgs::String>("chatter");

      using namespace std::chrono_literals;
      int i = 0;
      while (talos::Ok()) {
        talos::msgs::String msg;
        msg.data = "hello #" + std::to_string(i++);
        pub.Publish(msg);
        TALOS_INFO("publish %s -> %s", msg.data.c_str(), pub.key().c_str());
        std::this_thread::sleep_for(500ms);
      }
      return 0;
    }
    ```

    subscriber：

    ```cpp
    #include "talosos/logging.h"
    #include "talosos/messages.h"
    #include "talosos/node.h"

    int main(int argc, char** argv) {
      talos::Init(argc, argv);
      auto node = talos::Node::Create("hello_listener");
      auto sub = node->Subscribe<talos::msgs::String>(
          "chatter", [](const talos::msgs::String& msg) {
            TALOS_INFO_STREAM("got: " << msg.data);
          });
      node->Spin();
      return 0;
    }
    ```

    `CMakeLists.txt` 注册：

    ```cmake
    find_package(TalosOS REQUIRED)
    add_executable(hello_node src/hello_node.cc)
    target_link_libraries(hello_node PRIVATE TalosOS::talosos)
    add_executable(hello_listener src/hello_listener.cc)
    target_link_libraries(hello_listener PRIVATE TalosOS::talosos)
    install(TARGETS hello_node hello_listener
            RUNTIME DESTINATION lib/${PROJECT_NAME})
    ```

    构建并运行：

    ```bash
    talos build hello
    talos run hello hello_node &
    talos run hello hello_listener
    ```

=== "Python"

    publisher，`talker.py`：

    ```python
    #!/usr/bin/env python3
    import time
    from talosos.messages import String
    from talosos.runtime import Node, init, ok

    def main() -> None:
        init()
        node = Node.create("py_talker")
        pub = node.advertise("chatter", String)
        i = 0
        while ok():
            pub.publish(String(data=f"hello #{i}"))
            print(f"publish hello #{i} -> {pub.key}")
            i += 1
            time.sleep(0.5)

    if __name__ == "__main__":
        main()
    ```

    subscriber，`listener.py`：

    ```python
    from talosos.messages import String
    from talosos.runtime import Node, init

    def main() -> None:
        init()
        node = Node.create("py_listener")
        node.subscribe("chatter", String, lambda m: print("got:", m.data))
        node.spin()

    if __name__ == "__main__":
        main()
    ```

    两个文件任意放在 `examples/python/` 或功能包的 `scripts/`，直接
    `python3 talker.py` / `python3 listener.py` 即可。

    !!! tip "订阅对象自动持有"

        `node.subscribe(...)` 返回的 `Subscription` 会被 Node 内部列表
        引用 —— 即便你不保留返回值也不会被 GC。与 rclpy 约定一致。

## 类风格节点（ROS1 成员变量）

把 publisher / subscription / 状态封装到类里 —— 最接近 ROS1 的写法。

=== "C++"

    ```cpp
    class ChatterNode {
     public:
      ChatterNode(std::shared_ptr<talos::Node> node)
          : node_(std::move(node)) {
        // 成员 Publisher 是非模板化的 —— 只在 Advertise<T>() 点写 T。
        chatter_pub_ = node_->Advertise<talos::msgs::Int64>("chatter");
        reset_sub_   = node_->Subscribe("reset",
                                          &ChatterNode::OnReset, this);
      }

      void PublishOnce() {
        talos::msgs::Int64 m; m.data = ++count_;
        chatter_pub_.Publish(m);
      }

     private:
      void OnReset(const talos::msgs::Empty&) {
        TALOS_LOG(INFO) << "reset by /reset";
        count_ = 0;
      }

      std::shared_ptr<talos::Node> node_;
      talos::Publisher chatter_pub_;          // 注意：无 <T>
      talos::Subscription reset_sub_;
      int64_t count_ = 0;
    };

    int main(int argc, char** argv) {
      talos::Init(argc, argv);
      ChatterNode node(talos::Node::Create("chatter"));
      while (talos::Ok()) {
        node.PublishOnce();
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
      }
    }
    ```

    完整示例在 `examples/cpp/class_demo/`。

=== "Python"

    ```python
    from talosos.messages import Empty, Int64
    from talosos.runtime import Node, init, ok

    class ChatterNode:
        def __init__(self, node: Node) -> None:
            self.node = node
            self.count = 0
            self.pub = node.advertise("chatter", Int64)
            self.sub = node.subscribe("reset", Empty, self.on_reset)

        def on_reset(self, _msg: Empty) -> None:
            print("reset by /reset")
            self.count = 0

        def publish_once(self) -> None:
            self.count += 1
            self.pub.publish(Int64(data=self.count))

    def main() -> None:
        init()
        chat = ChatterNode(Node.create("chatter"))
        import time
        while ok():
            chat.publish_once()
            time.sleep(0.5)

    if __name__ == "__main__":
        main()
    ```

    完整示例在 `examples/python/class_demo.py`。

## 三种回调绑定写法（仅 C++）

`Subscribe` 重载支持三种等价写法，按喜好挑一个：

```cpp
// (a) 成员函数指针 —— 最简洁，与 ROS1 风格一致
reset_sub_ = node_->Subscribe("reset", &ChatterNode::OnReset, this);

// (b) 带 this 捕获的 lambda
reset_sub_ = node_->Subscribe<talos::msgs::Empty>(
    "reset", [this](const talos::msgs::Empty& m) { OnReset(m); });

// (c) std::bind（传统但偶尔用得上，比如预绑定额外参数）
reset_sub_ = node_->Subscribe<talos::msgs::Empty>(
    "reset", std::bind(&ChatterNode::OnReset, this, std::placeholders::_1));
```

Python 没有这层区分 —— 任何可调用对象都可以传给 `subscribe()`。

## 话题名与命名空间

话题名采用 ROS 约定：

| 写法 | 解析后的绝对键名（节点叫 `chatter`，ns 为空） |
|---|---|
| `"/foo"` | `foo` |
| `"foo"` | `chatter/foo`（相对于节点私有命名空间） |
| `"~foo"` | `chatter/foo`（同上，显式私有） |

构造节点时可以传 `NodeOptions{.ns = "/robot0"}`，之后相对话题自动变成
`/robot0/chatter/foo`。用 `node->ResolveTopic("foo")` 可以显式求解。

## 跨语言互通

所有消息都走 **CDR 编码**，与 ROS2 兼容。C++ publisher ↔ Python subscriber
完全等价（反向也可）：

```bash
# 终端 1 (C++)
./build/examples/cpp/talker

# 终端 2 (Python)
python3 examples/python/listener.py
# → 收到 hello #0 hello #1 ...
```

| 侧 A | 侧 B | 是否互通 |
|---|---|---|
| C++ talker  | C++ listener   | ✅ |
| C++ talker  | Python listener | ✅ |
| Python talker | C++ listener | ✅ |
| Python talker | Python listener | ✅ |

## 常见陷阱

- **忘了 `talos::Init(argc, argv)`**：没装 SIGINT 处理器，`Ok()` 永远 true，
  Ctrl-C 无效。
- **Publisher 生命周期结束太早**：`auto pub = …; {...}` 离开作用域后
  `pub` 析构，再发布报错。把 publisher 作为成员变量（类风格）或长期
  变量持有。
- **话题名含空格 / 大写开头**：话题名建议用小写 + 下划线 + 斜杠，避免
  zenoh 键匹配歧义。
- **回调里阻塞**：zenoh 回调线程被阻塞会积压消息。重活丢到 worker 线程
  或用 `SpinOnce()` 自己管节奏。

## 相关

- [示例二：服务编程](service.md) —— 请求/响应模式
- [示例四：自定义消息](custom-messages.md) —— 用自己的 `.msg`
- [rqt / viz 工具箱](rqt.md) —— 可视化 topic 列表与数据
