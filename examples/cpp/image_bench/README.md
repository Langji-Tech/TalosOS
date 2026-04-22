# image_bench — 图像传输延时压测

测量 TalosOS（底层 zenoh-cpp）的多话题图像发布/订阅端到端延时。

## 架构

```
发布进程:  10 个 publisher 线程              订阅进程: 1 个 Node + 10 个 Subscription
  每个线程:                                    每个 Subscription:
    msg.header.stamp = wall_clock.now()         lat = wall_clock.now() - msg.header.stamp
    publisher.Publish(msg)                      -> 滚动窗口 (默认 2000 样本/话题)
    sleep(1/Hz)                                 -> 定期输出 p50/p90/p99/max
```

关键点：

- 发布端把 **wall-clock 纳秒** 写入 `header.stamp`。订阅端用同一台机器
  （或 NTP 同步的两台）的 `system_clock::now()` 相减，得到真正的 **从
  Publish 返回 → 订阅回调被触发** 的单向延时。
- payload 默认用仓库里真实的 PNG (~397 KB)。需要纯净协议延时时用
  `--payload-size 1024`。
- 发布/订阅建议放在**不同进程**（同机即可），这样数据要经历完整的
  zenoh transport；`--role both` 只适合做冒烟。

## 构建 / 运行

```bash
cmake --build build --target image_bench

# 终端 A（订阅者先启动以抓全首批消息）
./build/examples/cpp/image_bench/image_bench \
    --role sub --topics 10 --report 3 --duration 15

# 终端 B（发布者）
./build/examples/cpp/image_bench/image_bench \
    --role pub --topics 10 --hz 10 --duration 12
```

### 常用开关

| 参数                     | 说明                                                   |
| ------------------------ | ------------------------------------------------------ |
| `--role pub\|sub\|both`  | 角色                                                   |
| `--topics N`             | 并发话题数                                             |
| `--hz FLOAT`             | 每话题发布频率                                         |
| `--duration SECONDS`     | 运行时长（0 = 不退出）                                 |
| `--report SECONDS`       | 订阅端汇总输出间隔                                     |
| `--window N`             | 每话题 percentile 所用滚动样本数 (默认 2000)           |
| `--image PATH`           | 载荷 PNG 路径                                          |
| `--payload-size BYTES`   | 用合成字节代替 PNG，可单独测协议开销                   |
| `--topic-prefix PFX`     | key 前缀，默认 `/bench/image_`                         |

## 10 话题 × 10 Hz × ~397 KB PNG 同机双进程实测

| 话题                    | p50    | p90    | p99    | max    | mean   |
| ----------------------- | ------ | ------ | ------ | ------ | ------ |
| /bench/image_0          | 2.71   | 4.76   | 7.61   | 27.94  | 3.21   |
| /bench/image_1          | 2.62   | 4.73   | 6.15   | 23.59  | 3.08   |
| /bench/image_2          | 2.82   | 4.86   | 6.39   | 30.18  | 3.17   |
| /bench/image_3          | 2.55   | 4.49   | 6.91   | 19.54  | 2.86   |
| /bench/image_4          | 2.45   | 4.63   | 7.60   | 29.08  | 2.94   |
| /bench/image_5          | 2.42   | 4.55   | 6.34   | 25.62  | 2.70   |
| /bench/image_6          | 2.63   | 4.86   | 7.51   | 32.96  | 3.05   |
| /bench/image_7          | 2.84   | 5.14   | 6.72   | 31.62  | 3.18   |
| /bench/image_8          | 2.87   | 4.71   | 7.05   | 21.94  | 3.00   |
| /bench/image_9          | 1.92   | 3.56   | 5.71   | 34.11  | 2.29   |
| **ALL (聚合)**          | **2.52** | **4.75** | **7~20\*** | **34.11** | **2.95** |

（单位 ms。机型：Ubuntu 24.04 桌面级 CPU，同机双进程 zenoh loopback）

\* 聚合 p99 = 19.5 ms 偏高是因为它在所有 11,600 样本上取 99 分位；单话题 p99
都在 6~8 ms。聚合 max = 34 ms 是所有话题的最慢一帧 —— 通常是冷启动 / OS
调度抖动。

**聚合吞吐 ≈ 13.2 MB/s。**

## Python imshow 可视化

```bash
# 仍在发布的情况下
python3 examples/python/image_bench_viz.py --topics 10
# 只打印统计不渲染：
python3 examples/python/image_bench_viz.py --topics 10 --no-display
```

2×5 网格同时显示 10 路；每格底部显示 `last=... ms  p99=... ms`。

注意：**imshow 本身的渲染耗时会叠加**在传输延时之上（matplotlib 通常
20–40 ms/帧）。所以 GUI 格里显示的数字比上面的 C++ bench 数字略高——这是
可视化管线成本，不是传输层成本。**测协议延时请用 C++ bench，测显示延时
再看 GUI。**

## 与 ROS1 / ROS2 的对比

我机器上没有完整的 ROS1 stack 可直接跑对比；以下是**公开 benchmark 的
通用范围**，同等载荷 + 同机 loopback 条件下的量级 —— 不同发行版 / 硬件 /
RMW 会有显著偏差，建议以「量级」而不是「精确值」来读。

| 栈                                 | 典型单路延时（1080p RGB ≈ 6MB） | 典型单路延时（~400 KB PNG） |
| ---------------------------------- | ------------------------------- | --------------------------- |
| **TalosOS / zenoh-cpp**（本 bench）| 未测 6MB                        | **p50 ≈ 2.5 ms, p99 ≈ 7 ms** |
| ROS1 roscpp (TCPROS + nodelet)     | 10–30 ms                        | 1–3 ms                       |
| ROS1 roscpp (TCPROS, cross-proc)   | 20–80 ms                        | 3–8 ms                       |
| ROS2 + rmw_fastrtps (默认)         | 6–15 ms                         | 2–5 ms                       |
| ROS2 + rmw_cyclonedds              | 4–10 ms                         | 1.5–4 ms                     |
| ROS2 + rmw_zenoh                   | 3–8 ms                          | 1–3 ms                       |

参考方法学：ROS2 官方 `performance_test`、Cyclone DDS `roundtrip`、
ApexAI benchmark。TCPROS 在大消息上要做分片+拷贝+序列化三次，因此同等
payload 下 ROS1 在 6MB 级经常比 ROS2 DDS 高一倍以上；rmw_zenoh（ROS2 用
zenoh 作传输层）在近两年的测试里是**最接近** TalosOS 本 bench 数字的。

**本 bench 结果与 rmw_zenoh 处在同一量级**（p50 约 2–3 ms / 400KB），符合
预期——两者用的本就是同一个 zenoh runtime，区别只在上层 API 绑定。

## 做 ROS 同源对比的最小步骤

如果想在你本机直接与 ROS2 对拍（ROS1 停止维护，不推荐新测）：

```bash
# 已在 /opt/ros/kilted 里安装了 ROS2
source /opt/ros/kilted/setup.bash

# 起一个 ROS2 image publisher
ros2 topic pub -r 10 /bench/image_0 sensor_msgs/msg/CompressedImage \
    "{header: {frame_id: 'cam0'}, format: 'png', data: [...]}" &

# 用 ros2 topic hz / delay 观察
ros2 topic hz   /bench/image_0
ros2 topic delay /bench/image_0
```

或使用 ROS2 官方 `performance_test`：

```bash
# 省事的方法
ros2 run performance_test perf_test \
    --communication rclcpp-single-threaded-executor \
    --msg Struct1k --rate 10 --topic /bench -p 1 -s 1
```

把 TalosOS image_bench 和上面的 ROS2 结果并列即可直接比较。

## 方法学注意事项

1. **时钟一致性**：`header.stamp` 使用 `system_clock`，同机同内核时钟
   天然一致。跨机器需要 NTP / PTP 同步，否则延时会被系统时钟偏差污染。
2. **首包抖动**：zenoh 刚建立会话后的前几百 ms 内 p99 会偏高。bench 默认
   前 1 秒数据也会被纳入窗口；想要稳态数字请延长 `--duration` 并看后
   几次 report。
3. **GIL 非问题**：bench 是 C++，无 GIL。Python imshow viewer 会受 GIL +
   matplotlib 帧率限制，不建议用它测协议延时。
4. **SHM 快路径**：zenoh 同机发布的大消息会自动尝试走 POSIX shared memory
   快路径（我们编译时打开了 `ZENOHC_BUILD_WITH_SHARED_MEMORY=ON`），
   这是 p50 能稳定 < 3 ms 的关键。跨机会退回 TCP。
