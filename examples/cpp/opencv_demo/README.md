# opencv_demo — TalosOS 版的 `cv_bridge`

演示 `cv::Mat` ↔ `talos::msgs::Image` / `talos::msgs::CompressedImage` 的互转。
所有转换函数都在 `include/talosos/adapters/opencv.h`（header-only，要求下游
链接 OpenCV）。

## ROS `cv_bridge` ↔ TalosOS 对照表

| ROS                                        | TalosOS                                             |
| ------------------------------------------ | --------------------------------------------------- |
| `#include <cv_bridge/cv_bridge.h>`         | `#include "talosos/adapters/opencv.h"`              |
| `cv_bridge::CvImage`                       | 不需要（直接用 `cv::Mat` + `msgs::Header`）         |
| `cv_bridge::toImageMsg(mat, enc, header)`  | `talos::adapters::ToImageMessage(mat, enc, header)` |
| *（自动推导编码）*                         | `ToImageMessage(mat, header)` —— 从 `mat.type()` 推导 |
| `cv_bridge::toCvCopy(msg, "bgr8")`         | `ToCvMat(msg).clone()` —— 先视图后 clone            |
| `cv_bridge::toCvShare(msg, "bgr8")`        | `ToCvMat(msg)` —— **零拷贝视图**                    |
| `sensor_msgs::image_encodings::BGR8`       | 字符串字面量 `"bgr8"`（约定一致）                    |
| cv_bridge 内置 PNG/JPG codec               | `ToCompressedImageMessage(mat, "jpg")` +           |
|                                            | `ToCvMat(CompressedImage)` —— 底层即 `cv::imencode` / `imdecode` |

## 支持的 encoding 自动映射

`cv_bridge` 里那一长串 encoding 枚举，这里用纯字符串 + 查表处理。

| `cv::Mat::type()` | encoding 字符串 |
| ----------------- | --------------- |
| CV_8UC1           | `mono8`         |
| CV_8UC3           | `bgr8`          |
| CV_8UC4           | `bgra8`         |
| CV_16UC1          | `mono16`        |
| CV_16UC3          | `bgr16`         |
| CV_32FC1/2/3/4    | `32FC1/2/3/4`   |
| CV_64FC1/3        | `64FC1/3`       |
| 其他              | 通用 `<depth>C<channels>`（如 `8S C2`、`16S C1`） |

反向（`EncodingToCvType`）同时接受 `rgb8`/`bgr8`、`rgba8`/`bgra8` 等 ROS
常见同义词。

## 典型用法

### 发布 raw Image

```cpp
#include <opencv2/opencv.hpp>
#include "talosos/adapters/opencv.h"
#include "talosos/node.h"

cv::Mat bgr = cv::imread("photo.png", cv::IMREAD_COLOR);

auto node = talos::Node::Create("cam");
auto pub  = node->Advertise<talos::msgs::Image>("/cam/image_raw");

talos::msgs::Header h;
h.stamp = talos::Time::Now();
h.frame_id = "cam";

auto msg = talos::adapters::ToImageMessage(bgr, h);    // encoding 自动 bgr8
pub.Publish(msg);
```

### 订阅 raw Image

```cpp
auto sub = node->Subscribe<talos::msgs::Image>(
    "/cam/image_raw", [](const auto& msg) {
      cv::Mat view = talos::adapters::ToCvMat(msg);     // 零拷贝视图
      cv::imshow("cam", view);
      cv::waitKey(1);
    });
```

!!! note "视图 vs 拷贝"
    `ToCvMat(const Image&)` 返回一个**别名 msg.data 的 view**，**不要**在
    回调返回后继续使用它（回调结束 payload 就释放）。需要跨回调保留时
    调用 `ToCvMat(msg).clone()`。

### 压缩路径（JPEG / PNG）

```cpp
// 发布端：cv::Mat -> JPEG（quality=85）
auto jpeg = talos::adapters::ToCompressedImageMessage(
    mat, "jpg", header,
    {cv::IMWRITE_JPEG_QUALITY, 85});
pub_jpeg.Publish(jpeg);

// 订阅端：CompressedImage -> cv::Mat
auto sub = node->Subscribe<talos::msgs::CompressedImage>(
    "/cam/image/compressed", [](const auto& msg) {
      cv::Mat mat = talos::adapters::ToCvMat(msg);     // cv::imdecode
      // ... use mat ...
    });
```

## 构建 / 运行本 demo

```bash
cmake --build build --target cv_publisher cv_subscriber

# 终端 A — 订阅者（检测到 $DISPLAY 就 imshow，否则每收到一帧写到 /tmp/）
./build/examples/cpp/opencv_demo/cv_subscriber 3

# 终端 B — 发布者，同时出 raw + JPEG 两路
./build/examples/cpp/opencv_demo/cv_publisher \
    /home/ubuntu24/Software/TalosOS/image.png 5.0 color
```

本地实测输出（headless）：

```
publisher:  cols=640 rows=480 encoding=bgr8
  frame 0  raw=921600B  jpeg=61523B       <- raw = 640*480*3, JPEG 压了 15×
subscriber: got Image  640x480  encoding=bgr8  step=1920  bytes=921600
            wrote /tmp/cv_demo_frame_0.png
            got CompressedImage format=jpg  decoded=640x480
```

## raw vs 压缩，什么时候用哪个？

| 场景                                | 选择                                         |
| ----------------------------------- | -------------------------------------------- |
| 同机 / 局域网 + 足够带宽（>100 MB/s）| **raw `Image`**（零编解码、p50 延时最低）    |
| 跨机、带宽紧张、JPG 可接受损失      | `CompressedImage` + `"jpg"`                  |
| 跨机、需无损                        | `CompressedImage` + `"png"`（压缩比 ~1.5–2×）|
| 深度图 / 16 位                      | raw `Image` + `mono16` 或 JP2 压缩           |

参考数字（本仓库 640×480 BGR PNG 来源图）：

| 格式                | 字节数   | encode 时延 |
| ------------------- | -------- | ------------ |
| raw bgr8            | 921,600  | 0            |
| JPEG q=85           | ~62 KB   | ~1 ms / 帧   |
| PNG                 | ~400 KB  | ~5 ms / 帧   |

raw 免编解码但流量大 15×；JPEG 压缩 15× 但 +1 ms/帧 + 不可逆；PNG 压缩
~2× 但 +5 ms/帧。这三种路径 TalosOS cv_bridge 都支持，单次函数调用切换。
