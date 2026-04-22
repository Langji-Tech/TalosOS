# 示例三：动作编程

动作 (action) 在 pub/sub 之上实现**长时间任务**模型，原生支持**周期反馈**
和**客户端取消**。对应 ROS 的 actionlib / rclcpp_action，最经典的例子是
导航（走到目标点）和机械臂抓取。

!!! note "Python 端"

    `talos::ActionServer` / `ActionClient` 目前只在 C++ 端提供一等公民封装
    （`include/talosos/action.h`）。Python 侧可以用基础 pub/sub **手动**
    订阅四个话题来做一个简化版 —— 下面 Python 标签页给了最小示例。

## 动作在 TalosOS 里的四条管道

每个动作名下自动拆解为**四个话题**：

| 话题 | 方向 | 作用 |
|---|---|---|
| `<action>/goal`     | 客户端 → 服务端 | 新目标，携带 128-bit `GoalID` |
| `<action>/feedback` | 服务端 → 客户端 | 周期进度（由 handler 自己节奏发）|
| `<action>/result`   | 服务端 → 客户端 | 最终结果 + `GoalStatus` |
| `<action>/cancel`   | 客户端 → 服务端 | 针对指定 `GoalID` 请求中止 |

`GoalID` 是 128-bit UUID，打印为 32 位十六进制。它让**同一个 action 可以
并发跑多个目标**；每个目标有独立的反馈通道与结果。

## Fibonacci — 最小动作

示例源码：`examples/cpp/fibonacci/{fibonacci_server,fibonacci_client}.cc`。

=== "C++ 服务端"

    ```cpp
    #include <chrono>
    #include <thread>

    #include "talosos/action.h"
    #include "talosos/logging.h"
    #include "talosos/node.h"
    #include "fibonacci/action/FibonacciGoal.h"
    #include "fibonacci/action/FibonacciFeedback.h"
    #include "fibonacci/action/FibonacciResult.h"

    using namespace fibonacci::action;
    using Server = talos::ActionServer<FibonacciGoal, FibonacciFeedback, FibonacciResult>;

    int main(int argc, char** argv) {
      talos::Init(argc, argv);
      auto node = talos::Node::Create("fib_server");

      auto server = talos::MakeActionServer<FibonacciGoal, FibonacciFeedback, FibonacciResult>(
          node, "/fibonacci",
          [](Server::Handle& h) -> std::pair<talos::GoalStatus, FibonacciResult> {
            std::vector<int32_t> seq = {0, 1};
            for (int32_t i = 2; i <= h.goal().order; ++i) {
              if (h.canceling()) {
                FibonacciResult partial; partial.sequence = seq;
                return {talos::GoalStatus::kCanceled, partial};
              }
              seq.push_back(seq[i - 1] + seq[i - 2]);
              FibonacciFeedback fb; fb.partial_sequence = seq;
              h.PublishFeedback(fb);
              std::this_thread::sleep_for(std::chrono::milliseconds(200));
            }
            FibonacciResult r; r.sequence = seq;
            return {talos::GoalStatus::kSucceeded, r};
          });

      node->Spin();
      return 0;
    }
    ```

    服务端为**每个进来的目标**开一个独立 worker 线程；`h.canceling()` 在
    客户端发送匹配的 `Cancel` 之后翻成 `true`，execute 函数应轮询该标志
    及时收尾。

=== "C++ 客户端"

    ```cpp
    #include "talosos/action.h"
    #include "talosos/logging.h"
    #include "talosos/node.h"

    using namespace fibonacci::action;

    int main(int argc, char** argv) {
      talos::Init(argc, argv);
      auto node = talos::Node::Create("fib_client");
      auto client = talos::MakeActionClient<
            FibonacciGoal, FibonacciFeedback, FibonacciResult>(
          node, "/fibonacci");

      FibonacciGoal goal; goal.order = 20;
      auto handle = client.SendGoal(goal,
          [](const FibonacciFeedback& fb) {
            TALOS_INFO("feedback len=%zu", fb.partial_sequence.size());
          });

      FibonacciResult result;
      talos::GoalStatus status;
      if (handle->WaitForResult(std::chrono::seconds(15), result, status)) {
        TALOS_INFO("final: %s, tail=%d",
                    talos::ToString(status),
                    result.sequence.back());
      }
      return 0;
    }
    ```

=== "Python（手动 pub/sub 版）"

    Python 运行时暂未封装 Action API。用 topic 手动拼装一个最小客户端：

    ```python
    # 订阅 /fibonacci/feedback 与 /fibonacci/result，发 /fibonacci/goal
    import time, uuid, struct
    from talosos.runtime import Node, init
    from talosos.cdr import CdrReader
    # 用 talos_msg_gen 生成的 Python 绑定加载 FibonacciGoal / Feedback / Result

    init()
    node = Node.create("fib_py_client")
    goal_pub = node.advertise("/fibonacci/goal", FibonacciGoal)
    node.subscribe("/fibonacci/feedback", FibonacciFeedback,
                    lambda fb: print("fb len=", len(fb.partial_sequence)))
    node.subscribe("/fibonacci/result", FibonacciResult,
                    lambda r: print("done, tail=", r.sequence[-1]))

    # 真正的 Goal 消息有 goal_id 字段；简化版这里略去取消逻辑
    time.sleep(0.3)
    goal_pub.publish(FibonacciGoal(order=20))
    node.spin()
    ```

    完整的 goal_id / cancel 流程要等 Python Action SDK 完成；此方案适合做
    "只发目标 + 看反馈"的单次用法。

## 取消目标

客户端拿到 `handle` 后可以随时 `handle->Cancel()`：

```cpp
auto handle = client.SendGoal(goal, feedback_cb);
std::this_thread::sleep_for(std::chrono::seconds(1));
handle->Cancel();    // 服务端 h.canceling() 变 true
```

服务端一定要**周期性检查** `h.canceling()`。如果忘了检查，cancel 对长耗时
任务不生效。

## GoalStatus 取值

```cpp
namespace talos {
enum class GoalStatus {
  kUnknown, kAccepted, kExecuting, kCanceling,
  kSucceeded, kAborted, kCanceled, kRejected
};
const char* ToString(GoalStatus);
}
```

- `kAccepted / kExecuting` —— 执行中（kExecuting 在 handler 开始跑之后）
- `kSucceeded` —— handler 返回 `{kSucceeded, result}`
- `kCanceled`  —— handler 看到 `canceling()` 后返回 `{kCanceled, partial}`
- `kAborted`   —— handler 抛异常 / 返回 `{kAborted, ...}`
- `kRejected`  —— （保留）服务端拒绝目标，目前未实现拒绝回调

## 动作 vs 服务 vs 话题

| 模式 | 选它的时候 |
|---|---|
| **话题** | 数据天然连续：传感器流、控制指令 |
| **服务** | 1 秒内算完的同步请求：加法、开关某个 flag、查参数 |
| **动作** | 分钟级任务：导航到目标、执行轨迹、上下料流程；你需要看进度、能中途取消 |

**别用服务做长任务**。服务的客户端是阻塞等待，远端一直不回客户端就永远
挂着；用动作至少能周期反馈 + 主动取消。

## 相关

- [示例二：服务编程](service.md) —— 短请求用它
- [示例一：话题编程](topic.md) —— 动作底层也是四个 topic
- [Launch 启动文件](launch.md) —— 一次起服务端 + 客户端
