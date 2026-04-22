# 进阶：图像延时 / 丢帧基准

!!! note "前置阅读"

    本章是 [示例五 · 图像传输 / cv_bridge](image-transport.md) 的深入篇，
    聚焦在**怎么量化一条图像链路的性能**。如果你只想知道怎么发图像，去
    看那章就够了；本章面向已经在用、想做回归基准的读者。

TalosOS 自带一个针对视频流的基准工具，用来回答两个问题：

1. **这条链路有没有丢帧？** 丢了多少？
2. **端到端延时多少？** p50 / p90 / p99 / max 各是多少？

源码：`examples/cpp/image_bench/image_bench.cc`（C++）
可视化：`examples/python/image_bench_viz.py`（可选）

## 怎么用

`image_bench` 同时支持三种角色：

```bash
# 纯发布端
./build/examples/cpp/image_bench/image_bench \
    --role pub --topics 4 --hz 30

# 纯订阅端（另一台机或另一个终端）
./build/examples/cpp/image_bench/image_bench \
    --role sub --topics 4 --report 2.0

# 同进程对跑（仅 sanity check，不能代表真实部署）
./build/examples/cpp/image_bench/image_bench \
    --role both --topics 4 --hz 30 --duration 20
```

常用参数：

| 参数 | 说明 |
|---|---|
| `--topics N` | 并发路数，模拟多相机 |
| `--hz R` | 发布频率 |
| `--image PATH` | 用指定 PNG 做 payload（默认用仓库自带图） |
| `--payload-size N` | 合成 payload（纯噪声），覆盖 `--image` |
| `--duration S` | 运行秒数后自动退出 |
| `--report S` | 订阅端统计打印间隔 |

## 输出解读

订阅端每 `--report` 秒打印一行：

```
rx=302  rate=30.02 Hz  drops(seq)=0  drops(gap~win)=0
  lat_ms p50=1.8 p90=3.1 p99=4.7 max=9.2
```

| 字段 | 含义 |
|---|---|
| `rx` | 累计收到帧数 |
| `rate` | 最近滑动窗口的实测频率 |
| `drops(seq)` | **精确丢帧数** —— publisher 在 `header.frame_id` 里塞了序号，通过序号跳变计数 |
| `drops(gap~win)` | 按"帧间隔 > 1.5× 平均间隔"估算的丢帧 |
| `lat_ms *` | 端到端延时（publisher `header.stamp` → subscriber 回调触发） |

!!! warning "跨设备延时需要时间同步"

    `lat_ms` 是两端 wall-clock 差。同机运行时钟天然一致；**跨设备必须先 NTP / PTP
    同步**，否则数值会被时钟偏移污染。

## 典型诊断

| 现象 | 判定 |
|---|---|
| `drops(seq)=0` 且 `drops(gap~win)=0` | 链路无丢帧 |
| 两个 drop 数大致一致且 > 0 | 真丢帧，通常是单核带宽打满（1080p RGB 原始流 ~180 MB/s） |
| `drops=0` 但 `rate` 远低于 `--hz` | 瓶颈在 publisher 侧（采集 / 编码 / sleep），不是传输 |
| `p99 ≫ p50`（10×+） | 抖动，常见原因是 GIL 或 CPU 抢占 |

## 何时用基准工具，何时自己测

`image_bench` 用自己的 `/bench/image_<i>` 话题，适合**量化整条链路的极限能力**。

如果你想测**自己业务 topic**（比如 `/camera/image/rgb`），抄一份订阅端逻辑进你自己
的节点更合适，参考:

- `examples/cpp/image_bench/image_bench.cc` 里的 `Metrics` / 滚动窗口统计
- `drops(seq)` 需要发布端配合：`msg.header.frame_id = "cam#" + std::to_string(seq++);`

## 相关教程

- [示例五 · 图像传输 / cv_bridge](image-transport.md) —— 图像 pub/sub + `cv::Mat` 互转
- [性能基准](../reference/benchmarks.md) —— 参考数值
