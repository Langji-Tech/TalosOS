# 示例五：图像传输 / cv_bridge

图像流是机器人系统最常见的高带宽话题之一。TalosOS 支持两种图像消息：

| 消息类型 | 载荷 | 适用 |
|---|---|---|
| `Image`           | 原始像素数据 + encoding 字段 | 本地高帧率、单机处理、有 SHM 时 |
| `CompressedImage` | JPEG/PNG 编码好的字节 | **跨网络推荐** —— 省 10–50× 带宽 |

## 最小图像 pub / sub

### 发布端

=== "C++"

    ```cpp
    #include <fstream>
    #include <sstream>
    #include <chrono>
    #include <thread>

    #include "talosos/logging.h"
    #include "talosos/messages.h"
    #include "talosos/node.h"

    // 读取 png 到 CompressedImage 然后发布
    int main(int argc, char** argv) {
      if (argc < 2) return 2;
      talos::Init(argc, argv);
      auto node = talos::Node::Create("image_pub");
      auto pub = node->Advertise<talos::msgs::CompressedImage>(
            "/camera/image/compressed");

      std::ifstream f(argv[1], std::ios::binary);
      std::ostringstream buf; buf << f.rdbuf();
      const std::string png = buf.str();

      using namespace std::chrono_literals;
      int seq = 0;
      while (talos::Ok()) {
        talos::msgs::CompressedImage msg;
        msg.header.frame_id = "cam#" + std::to_string(seq++);
        msg.header.stamp    = talos::Time::Now();
        msg.format = "png";
        msg.data.assign(png.begin(), png.end());
        pub.Publish(msg);
        std::this_thread::sleep_for(33ms);   // ~30 Hz
      }
    }
    ```

=== "Python"

    ```python
    #!/usr/bin/env python3
    import sys, time
    from pathlib import Path
    from talosos.messages import CompressedImage, Header, Time as TMsg
    from talosos.runtime import Node, init, ok

    def main() -> None:
        png = Path(sys.argv[1]).read_bytes()
        init()
        node = Node.create("image_pub_py")
        pub = node.advertise("/camera/image/compressed", CompressedImage)

        seq = 0
        while ok():
            now = time.time_ns()
            msg = CompressedImage(
                header=Header(frame_id=f"cam#{seq}",
                                stamp=TMsg(sec=now // 1_000_000_000,
                                             nanosec=now % 1_000_000_000)),
                format="png",
                data=png)
            pub.publish(msg)
            seq += 1
            time.sleep(1 / 30)

    if __name__ == "__main__":
        main()
    ```

### 订阅端

=== "C++"

    ```cpp
    #include <opencv2/opencv.hpp>

    #include "talosos/adapters/opencv.h"      // cv_bridge 适配器
    #include "talosos/messages.h"
    #include "talosos/node.h"

    int main(int argc, char** argv) {
      talos::Init(argc, argv);
      auto node = talos::Node::Create("image_sub");

      std::mutex mu;
      cv::Mat latest;

      auto sub = node->Subscribe<talos::msgs::CompressedImage>(
          "/camera/image/compressed",
          [&](const talos::msgs::CompressedImage& msg) {
            std::vector<uint8_t> buf(msg.data.begin(), msg.data.end());
            cv::Mat img = cv::imdecode(buf, cv::IMREAD_COLOR);
            std::lock_guard<std::mutex> lock(mu);
            latest = std::move(img);
          });

      while (talos::Ok()) {
        cv::Mat show;
        { std::lock_guard<std::mutex> lock(mu); show = latest; }
        if (!show.empty()) cv::imshow("cam", show);
        if (cv::waitKey(10) == 27) break;   // ESC 退出
      }
    }
    ```

    !!! danger "不要在回调里 imshow"

        `cv::imshow` 必须在**主线程**调用 —— zenoh 回调在后台线程跑。
        模式是：回调存 `cv::Mat`，主循环读最新值 + `imshow` + `waitKey`。

=== "Python"

    ```python
    import io
    from PIL import Image as PILImage
    import numpy as np

    from talosos.messages import CompressedImage
    from talosos.runtime import Node, init, ok

    def on_msg(msg: CompressedImage) -> None:
        img = PILImage.open(io.BytesIO(bytes(msg.data)))
        arr = np.asarray(img)
        print(f"got {arr.shape} frame, fid={msg.header.frame_id}")

    def main() -> None:
        init()
        node = Node.create("image_sub_py")
        node.subscribe("/camera/image/compressed", CompressedImage, on_msg)
        node.spin()

    if __name__ == "__main__":
        main()
    ```

## cv_bridge 互转（Image ↔ cv::Mat）

对于**原始 `Image`**（非 CompressedImage），TalosOS 提供与 ROS `cv_bridge`
等价的适配器 `talosos/adapters/opencv.h`：

```cpp
#include "talosos/adapters/opencv.h"

// === 发送端：cv::Mat → Image ===
cv::Mat bgr = cv::imread("scene.png", cv::IMREAD_COLOR);
auto msg = talos::adapters::ToImageMessage(bgr, "bgr8");  // encoding 字符串
msg.header.frame_id = "camera";
msg.header.stamp    = talos::Time::Now();
pub.Publish(msg);

// === 接收端：Image → cv::Mat（零拷贝视图） ===
node->Subscribe<talos::msgs::Image>("/camera/image/raw",
    [](const talos::msgs::Image& m) {
      cv::Mat view = talos::adapters::ToCvMat(m);    // 零拷贝
      cv::Mat own  = talos::adapters::ToCvMat(m).clone();  // 拥有副本
      // view 在回调返回后立即失效 —— 要跨线程用必须 .clone()
    });
```

支持的 `encoding`：`mono8 / 8uc1`、`rgb8 / bgr8 / 8uc3`、`rgba8 / bgra8 / 8uc4`。
`ToCvMat` 返回的 `cv::Mat` 用 `bgr8` 时**不自动做颜色空间转换**——按原字节
解释为 BGR。需要 RGB 请 `cv::cvtColor(mat, out, cv::COLOR_BGR2RGB)`。

## CompressedImage 怎么做

```cpp
// 发送端：cv::Mat → CompressedImage（JPEG 质量 85）
auto msg = talos::adapters::ToCompressedImageMessage(
    bgr, "jpeg", 85);   // 或 "png"；png 忽略 quality 参数
pub.Publish(msg);

// 接收端：CompressedImage → cv::Mat
node->Subscribe<talos::msgs::CompressedImage>("/cam/compressed",
    [](const talos::msgs::CompressedImage& m) {
      std::vector<uint8_t> buf(m.data.begin(), m.data.end());
      cv::Mat img = cv::imdecode(buf, cv::IMREAD_COLOR);
      // ...
    });
```

## 选型建议

| 场景 | 选 `Image` | 选 `CompressedImage` |
|---|---|---|
| 同机进程间，延时敏感（SLAM、控制环） | ✅ 零拷贝 ToCvMat 几十 ns | ❌ 解码开销 1-5ms |
| 跨网络（Wi-Fi、千兆） | ⚠️ 1080p × 30Hz ≈ 180 MB/s 挑战 NIC | ✅ JPEG q=85 约 60-80 KB/帧 |
| 录制 bag | ⚠️ 磁盘 IO 大 | ✅ 文件小 10-50× |
| 需要下游做 CV 运算 | ✅ 免解码 | ⚠️ 每帧先解码 |

## 测量延时 / 丢帧（image_bench）

仓库自带 `examples/cpp/image_bench/image_bench.cc`，是一个端到端基准工具：
同时启 N 路 publisher + N 路 subscriber，算每帧 p50/p90/p99 延时 + 序号丢帧
+ 实测频率。适合回答 **"我这条链路到底行不行"** 的问题。

```bash
# 终端 1：发布端（1080p × 4 路 × 30 Hz）
./build/examples/cpp/image_bench/image_bench --role pub --topics 4 --hz 30

# 终端 2：订阅端（另一台机器上）
./build/examples/cpp/image_bench/image_bench --role sub --topics 4 --report 2.0
```

输出：

```
rx=302  rate=30.02 Hz  drops(seq)=0  drops(gap~win)=0
  lat_ms p50=1.8 p90=3.1 p99=4.7 max=9.2
```

`drops(seq)` 是**精确丢帧数**（publisher 在 `header.frame_id` 里塞了
`cam#N` 序号，subscriber 检测跳变），`drops(gap~win)` 是按帧间隔估算的
补充指标。两个都 0 表示链路完美。

!!! warning "跨机延时需要时钟同步"

    `lat_ms` 是 publisher 发布时的 wall-clock 与 subscriber 回调触发时的
    wall-clock 之差。**必须先** NTP / chrony 同步两端（到 1ms 精度），否
    则数值被时钟偏移污染。同机则天然一致。

各字段判读与常见诊断（Wi-Fi 丢包、CPU 抢 GIL、TCP 重传）在
[图像延时 / 丢帧基准](image-bench.md) 小节。

## 常见陷阱

- **imshow 在回调线程**：OpenCV GUI 必须主线程，后台线程 imshow 会卡死。
  分离"存最新帧"与"显示"两件事。
- **`ToCvMat` 返回零拷贝视图**：msg 一出作用域就悬挂。跨线程用必须
  `.clone()`。
- **JPEG 编码是有损的**：做 SLAM / 立体匹配用 PNG 无损，或者走 `Image`。
- **encoding 字符串拼错**：`"rgb8"` / `"bgr8"` / `"mono8"` 严格区分，写错
  就颜色乱或尺寸对不上。

## 相关

- [功能包与构建](packages.md) —— CMake 里 `find_package(OpenCV REQUIRED)`
- [示例六：点云传输](pointcloud-io.md) —— 3D 数据走 PointCloud2
- [图像延时 / 丢帧基准](image-bench.md) —— 性能测量细节
- [rqt / viz 工具箱](rqt.md) —— `talos viz /topic --type Image` 实时显示
