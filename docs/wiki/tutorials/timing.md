# 定时与计时工具：Rate / Timer / tic-toc

做机器人编程绕不开四件事：**定频循环**、**周期回调**、**一次性延时**、
**测一段代码跑多久**。TalosOS 在 `include/talosos/rate.h` 和
`include/talosos/timer.h`（C++）与 `talosos.runtime`（Python）里把这四件
事封装成最小化的工具类，两端 API 对齐 ROS1 习惯，走 `std::chrono::
steady_clock` / `time.monotonic()`，不会被系统时钟跳变干扰。

| 场景 | 工具 |
|---|---|
| `while` 循环里以固定频率跑 | [`Rate`](#rate) |
| 后台周期性触发回调 | [`Timer`](#timer) |
| N 秒后跑一次 | `Timer(..., oneshot=True)` |
| 测 "这段代码跑了多久" | [`Stopwatch`](#stopwatch) / [`Tic/Toc`](#tic-toc) |
| RAII 语法糖："离开作用域时自动打印耗时" | [`ScopedTimer`](#scoped-timer) |

## <span id="rate"></span>Rate — 定频循环

=== "C++"

    ```cpp
    #include "talosos/rate.h"
    #include "talosos/node.h"

    int main(int argc, char** argv) {
      talos::Init(argc, argv);
      auto node = talos::Node::Create("ctrl");

      talos::Rate rate(50.0);   // 50 Hz
      while (talos::Ok()) {
        DoOneControlStep();
        if (!rate.Sleep()) {
          TALOS_WARN("fell behind: cycle took %.1f ms",
                      rate.cycle_time().count() / 1e6);
        }
      }
    }
    ```

    `Sleep()` 返回 `true` = 正常休眠；`false` = 本轮已经超时（没再睡）。
    调用后 `rate.cycle_time()` 反映上一轮实际花费。

=== "Python"

    ```python
    from talosos.runtime import Node, Rate, init, ok

    init()
    node = Node.create("ctrl")
    rate = Rate(50)                  # 50 Hz
    while ok():
        do_one_control_step()
        if not rate.sleep():
            print(f"fell behind: {rate.cycle_time*1000:.1f} ms")
    ```

    长时间初始化后要调 `rate.reset()`，否则第一轮 `sleep()` 会认为已经
    超时（因为 "上次唤醒时刻" 还是构造时那个）。

**与 ROS1 `ros::Rate` 的差异**：使用 `steady_clock`，系统时钟被 NTP
拉回/跳前不会影响循环节拍。

## <span id="timer"></span>Timer — 周期回调 / 一次性延时

ROS1 `ros::Timer` 的等价物：给一个周期和回调，后台线程定期调。**析构时
自动 cancel + join**，不泄漏。

=== "C++"

    ```cpp
    #include "talosos/timer.h"

    class MyController {
     public:
      MyController() {
        // 100Hz 控制环
        ctrl_timer_ = talos::Timer(100.0, [this] { OnControl(); });

        // 1Hz 心跳
        heartbeat_ = talos::Timer(std::chrono::seconds(1),
                                     [this] { OnHeartbeat(); });

        // 3 秒后执行一次的初始化延迟
        warmup_ = talos::Timer(std::chrono::seconds(3),
                                  [this] { FinishWarmup(); },
                                  /*oneshot=*/true);
      }

     private:
      void OnControl();
      void OnHeartbeat();
      void FinishWarmup();
      talos::Timer ctrl_timer_, heartbeat_, warmup_;
    };
    ```

    三种构造方式：

    - `Timer(double hz, cb, oneshot=false)` —— Hz（与 `Rate` 同）
    - `Timer(nanos period, cb, oneshot=false)` —— 任意 `std::chrono::`
      单位
    - `Timer()` 默认构造 + `operator=(Timer&&)` move 进来 —— 适合延迟
      启动

=== "Python"

    ```python
    from talosos.runtime import Node, Timer, init

    class MyController:
        def __init__(self, node):
            # 100Hz 控制环
            self.ctrl = Timer(0.01, self.on_control)

            # 1Hz 心跳
            self.heart = Timer(1.0, self.on_heartbeat)

            # 3 秒后一次性初始化
            self.warmup = Timer(3.0, self.finish_warmup, oneshot=True)

        def on_control(self):  ...
        def on_heartbeat(self): ...
        def finish_warmup(self): print("warmup done")

    init()
    node = Node.create("ctrl")
    c = MyController(node)
    node.spin()
    ```

    !!! warning "C++ 按 Hz，Python 按秒"

        C++ `Timer(double, cb)` 把 double 视作 **Hz**；Python
        `Timer(period_sec, cb)` 把它视作 **秒**。这是和语言习惯对齐
        的刻意选择（Python 的 `threading.Timer(interval, ...)` 也是秒）。
        C++ 如果你要按秒，用 `Timer(std::chrono::milliseconds(50), cb)`。

### 生命周期

把 `Timer` 作为**成员变量**或**长期局部变量**持有，就能保持回调活动。
引用失去时（类析构 / 离开作用域 / 被 move 覆盖）自动取消 + join。
回调里抛异常不会杀掉后台线程，异常会被捕获并打到 stderr。

显式停止：`timer.Cancel()` (C++) 或 `timer.cancel()` (Python)。幂等，多
次调用安全。

## <span id="stopwatch"></span>Stopwatch — 秒表

=== "C++"

    ```cpp
    #include "talosos/rate.h"   // Stopwatch 住在这里

    talos::Stopwatch sw;
    HeavyWork();
    TALOS_LOG(INFO) << "done in " << sw.milliseconds() << " ms";

    sw.Reset();                   // 重开计时
    MoreWork();
    auto ns = sw.elapsed();       // std::chrono::nanoseconds
    ```

    方法：`Reset() / elapsed() / seconds() / milliseconds() / microseconds()`。

=== "Python"

    ```python
    from talosos.runtime import Stopwatch

    sw = Stopwatch()
    heavy_work()
    print(f"done in {sw.milliseconds():.1f} ms")

    # with 块用法
    with Stopwatch() as sw2:
        do_stuff()
    print(f"block took {sw2.seconds():.3f} s")
    ```

## <span id="tic-toc"></span>tic / toc — MATLAB 风快速计时

每线程独立，无需维护变量：

=== "C++"

    ```cpp
    #include "talosos/rate.h"

    talos::Tic();
    LoadData();
    TALOS_LOG(INFO) << "load took " << talos::Toc() << " s";

    // 连续测几段：TocReset 返回上段耗时 + 自动 tic 下一段
    talos::Tic();
    Phase1(); double t1 = talos::TocReset();
    Phase2(); double t2 = talos::TocReset();
    Phase3(); double t3 = talos::Toc();
    TALOS_LOG(INFO) << "phases: " << t1 << "s " << t2 << "s " << t3 << "s";
    ```

=== "Python"

    ```python
    from talosos.runtime import tic, toc, toc_reset

    tic()
    load_data()
    print(f"load took {toc():.3f} s")

    tic()
    phase1(); t1 = toc_reset()
    phase2(); t2 = toc_reset()
    phase3(); t3 = toc()
    print(f"phases: {t1:.3f}s {t2:.3f}s {t3:.3f}s")
    ```

**线程安全**：每个 Python 线程 / C++ 线程有自己的 tic 点，互不干扰。

## <span id="scoped-timer"></span>ScopedTimer — RAII 打印耗时（仅 C++）

```cpp
{
  TALOS_SCOPED_TIMER("load image");
  cv::Mat img = cv::imread(path);
}
// → [load image] 12.3 ms  （自动打印，无需 Toc）
```

宏展开为一个栈上 `ScopedTimer` 对象，析构时 `TALOS_LOG(INFO)` 打印耗时。
Python 可以直接用 `with Stopwatch() as sw:`，效果等价（但打印要自己写）。

## 选型一览

| 你想做什么 | 用 |
|---|---|
| 在 while 循环里跑固定频率 | `Rate` |
| 后台每 N 秒自动调一个函数 | `Timer` |
| N 秒后做一次事 | `Timer(..., oneshot=True)` |
| 测一段同步代码的耗时 | `Stopwatch` 或 `Tic/Toc` |
| 某个作用域结束时自动打印耗时 | `TALOS_SCOPED_TIMER("label")` (C++) 或 `with Stopwatch()` (Python) |

## 常见陷阱

- **C++ `Timer(double, cb)` 是 Hz**，不是秒 —— 要按秒用
  `Timer(std::chrono::milliseconds(50), cb)`
- **Python `Timer(period_sec, cb)` 是秒**，不是 Hz —— 要按 Hz 用
  `Timer(1/hz, cb)`
- **Timer 被丢弃就停**：没有成员变量持有会被 GC / RAII 析构，回调不
  再触发
- **回调里 `Ok()` 失效后不自动停止**：退出循环时记得显式 `Cancel()`
  或让对象析构带走
- **`Rate.Sleep()` 不会唤醒响应 SIGINT**：循环外层应有 `while (Ok())`
  检查；单次 `Sleep()` 最多睡一个周期

## 相关

- [示例一 · 话题编程](topic.md) —— `Rate` 在 publisher 主循环里最常用
- [rqt / viz 工具箱](rqt.md) —— `RENDER_TICK_MS` 控制 UI 帧率的类似思路
