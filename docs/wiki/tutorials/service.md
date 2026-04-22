# 示例二：服务编程

服务 (service) 是**请求—响应**模式：客户端发出一个 request，服务端算出
一个 response 送回来。适合"做一次性计算"的场景（点个按钮、查询状态、触
发动作），**不适合**流式数据（那是话题的事）。

!!! tip "服务 vs 话题 vs 动作"

    | 模式 | 典型场景 | 延迟 |
    |---|---|---|
    | 话题 | 连续流（摄像头、激光、里程计） | 极低（fire-and-forget） |
    | **服务** | **同步计算（加法、置位、参数读写）** | **请求 → 响应往返** |
    | 动作 | 长任务（导航、抓取） | 秒 ~ 分钟，带反馈与取消 |

## AddTwoInts — 最小服务

用内置示例消息 `AddTwoInts{Request, Response}`，来源：
`examples/cpp/add_two_ints/`、`examples/python/add_two_ints_{server,client}.py`。

=== "C++"

    服务端：

    ```cpp
    #include "talosos/logging.h"
    #include "talosos/messages.h"
    #include "talosos/node.h"

    int main(int argc, char** argv) {
      talos::Init(argc, argv);
      auto node = talos::Node::Create("adder_server");
      auto svc = node->AdvertiseService<
            talos::msgs::AddTwoIntsRequest,
            talos::msgs::AddTwoIntsResponse>(
          "add_two_ints",
          [](const talos::msgs::AddTwoIntsRequest& req) {
            talos::msgs::AddTwoIntsResponse resp;
            resp.sum = req.a + req.b;
            TALOS_LOG(INFO) << req.a << " + " << req.b << " = " << resp.sum;
            return resp;
          });
      node->Spin();
      return 0;
    }
    ```

    客户端：

    ```cpp
    #include <cstdio>
    #include "talosos/messages.h"
    #include "talosos/node.h"

    int main(int argc, char** argv) {
      if (argc < 3) { std::puts("usage: add_client <a> <b>"); return 2; }
      talos::Init(argc, argv);
      auto node = talos::Node::Create("adder_client");
      auto client = node->CreateServiceClient<
            talos::msgs::AddTwoIntsRequest,
            talos::msgs::AddTwoIntsResponse>("add_two_ints");

      talos::msgs::AddTwoIntsRequest req;
      req.a = std::stoll(argv[1]); req.b = std::stoll(argv[2]);

      auto resp = client.Call(req, std::chrono::seconds(3));
      if (!resp) { std::puts("error: call timed out"); return 1; }
      std::printf("%lld + %lld = %lld\n",
                  (long long)req.a, (long long)req.b, (long long)resp->sum);
      return 0;
    }
    ```

    CMake 同 [话题编程](topic.md)，把源文件加进 `add_executable`。

=== "Python"

    服务端：

    ```python
    from talosos.messages import AddTwoIntsRequest, AddTwoIntsResponse
    from talosos.runtime import Node, init

    def handler(req: AddTwoIntsRequest) -> AddTwoIntsResponse:
        return AddTwoIntsResponse(sum=req.a + req.b)

    def main() -> None:
        init()
        node = Node.create("adder_server_py")
        node.advertise_service("add_two_ints",
                                AddTwoIntsRequest, AddTwoIntsResponse,
                                handler)
        node.spin()

    if __name__ == "__main__":
        main()
    ```

    客户端：

    ```python
    import sys
    from talosos.messages import AddTwoIntsRequest, AddTwoIntsResponse
    from talosos.runtime import Node, init

    def main() -> int:
        a, b = int(sys.argv[1]), int(sys.argv[2])
        init()
        node = Node.create("adder_client_py")
        client = node.create_service_client("add_two_ints",
                                             AddTwoIntsRequest,
                                             AddTwoIntsResponse)
        resp = client.call(AddTwoIntsRequest(a=a, b=b), timeout=3.0)
        if resp is None:
            print("timeout"); return 1
        print(f"{a} + {b} = {resp.sum}")

    if __name__ == "__main__":
        raise SystemExit(main())
    ```

运行方式（客户端可以跨语言随便配）：

```bash
# 终端 1 —— 服务端（C++ 或 Python，二选一）
./build/examples/cpp/add_two_ints/add_two_ints_server
# 或： python3 examples/python/add_two_ints_server.py

# 终端 2 —— 客户端
./build/examples/cpp/add_two_ints/add_two_ints_client 7 35
# 或： python3 examples/python/add_two_ints_client.py 7 35
# → 7 + 35 = 42
```

## 类风格服务

把 handler 作为成员函数。

=== "C++"

    ```cpp
    class Adder {
     public:
      Adder(std::shared_ptr<talos::Node> node) {
        svc_ = node->AdvertiseService<
               talos::msgs::AddTwoIntsRequest,
               talos::msgs::AddTwoIntsResponse>(
               "add_two_ints", &Adder::OnCall, this);
      }

     private:
      talos::msgs::AddTwoIntsResponse OnCall(
          const talos::msgs::AddTwoIntsRequest& req) {
        talos::msgs::AddTwoIntsResponse resp;
        resp.sum = req.a + req.b;
        return resp;
      }
      talos::Service svc_;
    };
    ```

=== "Python"

    ```python
    class Adder:
        def __init__(self, node: Node) -> None:
            self.svc = node.advertise_service(
                "add_two_ints", AddTwoIntsRequest, AddTwoIntsResponse,
                self.on_call)

        def on_call(self, req: AddTwoIntsRequest) -> AddTwoIntsResponse:
            return AddTwoIntsResponse(sum=req.a + req.b)
    ```

## 同步调用与超时

服务客户端是**同步**调用 —— `call(req, timeout)` 会阻塞直到拿到响应或
超时；超时返回 `nullptr` / `None`。

**长时间的工作请不要用服务**。服务超时一般设 1–3 秒；更长的任务用
[动作](action.md)，它能周期反馈进度并支持取消。

## CLI 调试

```bash
# 列出当前所有服务
talos service list

# 查看服务的广播类型 / 宿主节点
talos service info /add_two_ints

# 命令行直接调用（JSON 传参）
talos service call /add_two_ints --type AddTwoInts \
    --request '{"a": 7, "b": 35}'
# → response: {"sum": 42}
```

## 跨语言互通

服务的 request / response 编码与话题相同，全部走 CDR，**没有任何额外
约定**。C++ 服务端可以接受 Python 客户端的请求，反之亦然 —— 直接混搭：

```bash
# C++ server + Python client
./build/examples/cpp/add_two_ints/add_two_ints_server &
python3 examples/python/add_two_ints_client.py 100 23

# Python server + C++ client
python3 examples/python/add_two_ints_server.py &
./build/examples/cpp/add_two_ints/add_two_ints_client 7 35
```

## 常见陷阱

- **服务端未起就调用**：客户端立刻超时。`talos service list` 确认；
  也可以先 `talos service info <name>` 看到有节点再发请求。
- **handler 里阻塞 > timeout**：客户端超时返回空，handler 仍在跑。若
  handler 是重活，切到 [动作](action.md)。
- **Request/Response 类型写反**：模板参数顺序是 `<Req, Resp>`。类型对错了
  会在 CDR 反序列化报错。

## 相关

- [示例一：话题编程](topic.md)
- [示例三：动作编程](action.md) —— 长任务用这个
- [示例四：自定义消息](custom-messages.md) —— 定义自己的 .srv
