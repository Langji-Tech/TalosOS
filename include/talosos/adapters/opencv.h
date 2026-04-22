#ifndef TALOSOS_ADAPTERS_OPENCV_H_
#define TALOSOS_ADAPTERS_OPENCV_H_

// TalosOS equivalent of ROS `cv_bridge` — translate between `cv::Mat` and
// `talos::msgs::Image` / `talos::msgs::CompressedImage`. Header-only: the
// user must already link OpenCV (opencv_core + opencv_imgcodecs).
//
// Typical usage:
//
//   cv::Mat bgr = cv::imread("photo.png", cv::IMREAD_COLOR);
//   auto msg = talos::adapters::ToImageMessage(bgr);        // encoding auto-detected = "bgr8"
//   pub.Publish(msg);
//
//   // subscriber side
//   auto sub = node.Subscribe<talos::msgs::Image>("/cam", [](const auto& m) {
//     cv::Mat view = talos::adapters::ToCvMat(m);            // zero-copy view
//     cv::imshow("cam", view);
//   });
//
// For compressed paths use ToCompressedImageMessage(mat, "jpg"|"png") and
// ToCvMat(CompressedImage).

#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

#if __has_include(<opencv2/core.hpp>) && __has_include(<opencv2/imgcodecs.hpp>)
#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#define TALOSOS_HAVE_OPENCV 1
#else
#define TALOSOS_HAVE_OPENCV 0
#endif

#include "talosos/messages.h"

namespace talos::adapters {

#if TALOSOS_HAVE_OPENCV

// ---- Encoding <-> cv::Mat type mapping ----
//
// Matches sensor_msgs/image_encodings.h so payloads interop with ROS tools.

inline std::string CvTypeToEncoding(int cv_type) {
  switch (cv_type) {
    case CV_8UC1:  return "mono8";
    case CV_8UC3:  return "bgr8";    // OpenCV's default channel order
    case CV_8UC4:  return "bgra8";
    case CV_16UC1: return "mono16";
    case CV_16UC3: return "bgr16";
    case CV_32FC1: return "32FC1";
    case CV_32FC2: return "32FC2";
    case CV_32FC3: return "32FC3";
    case CV_32FC4: return "32FC4";
    case CV_64FC1: return "64FC1";
    case CV_64FC3: return "64FC3";
    default: {
      const int depth = CV_MAT_DEPTH(cv_type);
      const int channels = CV_MAT_CN(cv_type);
      const char* d = "?";
      switch (depth) {
        case CV_8U:  d = "8U";  break; case CV_8S:  d = "8S";  break;
        case CV_16U: d = "16U"; break; case CV_16S: d = "16S"; break;
        case CV_32S: d = "32S"; break; case CV_32F: d = "32F"; break;
        case CV_64F: d = "64F"; break;
      }
      return std::string(d) + "C" + std::to_string(channels);
    }
  }
}

inline int EncodingToCvType(const std::string& enc) {
  // Common ROS color / mono encodings.
  if (enc == "mono8"  || enc == "8UC1")  return CV_8UC1;
  if (enc == "mono16" || enc == "16UC1") return CV_16UC1;
  if (enc == "bgr8"   || enc == "rgb8" ||
      enc == "8UC3")                     return CV_8UC3;
  if (enc == "bgra8"  || enc == "rgba8" ||
      enc == "8UC4")                     return CV_8UC4;
  if (enc == "bgr16"  || enc == "rgb16" ||
      enc == "16UC3")                    return CV_16UC3;
  if (enc == "32FC1") return CV_32FC1;
  if (enc == "32FC2") return CV_32FC2;
  if (enc == "32FC3") return CV_32FC3;
  if (enc == "32FC4") return CV_32FC4;
  if (enc == "64FC1") return CV_64FC1;
  if (enc == "64FC3") return CV_64FC3;

  // Generic <depth>C<channels> fallback.
  const auto c_pos = enc.find('C');
  if (c_pos != std::string::npos) {
    const std::string d = enc.substr(0, c_pos);
    const int ch = std::stoi(enc.substr(c_pos + 1));
    int depth = -1;
    if (d == "8U")  depth = CV_8U;
    else if (d == "8S")  depth = CV_8S;
    else if (d == "16U") depth = CV_16U;
    else if (d == "16S") depth = CV_16S;
    else if (d == "32S") depth = CV_32S;
    else if (d == "32F") depth = CV_32F;
    else if (d == "64F") depth = CV_64F;
    if (depth >= 0 && ch >= 1 && ch <= 4) {
      return CV_MAKETYPE(depth, ch);
    }
  }
  throw std::runtime_error("TalosOS cv_bridge: unknown encoding '" + enc + "'");
}

// ---- cv::Mat -> msgs::Image ----

// Full control: caller supplies encoding explicitly (useful for rgb8 when the
// matrix is actually BGR, etc.).
inline msgs::Image ToImageMessage(const cv::Mat& image,
                                    std::string encoding,
                                    msgs::Header header = {}) {
  if (image.empty()) {
    throw std::runtime_error("TalosOS cv_bridge: empty cv::Mat");
  }
  if (!image.isContinuous()) {
    // Deep-copy so the wire payload has row_step == cols * elem_size and
    // the receiver can wrap a view over it directly.
    return ToImageMessage(image.clone(), std::move(encoding), std::move(header));
  }

  msgs::Image msg;
  msg.header = std::move(header);
  msg.width = static_cast<uint32_t>(image.cols);
  msg.height = static_cast<uint32_t>(image.rows);
  msg.encoding = std::move(encoding);
  msg.is_bigendian = 0;
  msg.step = static_cast<uint32_t>(image.step);
  msg.data.assign(image.datastart, image.dataend);
  return msg;
}

// Auto-detect encoding from the cv::Mat's type.
inline msgs::Image ToImageMessage(const cv::Mat& image,
                                    msgs::Header header = {}) {
  return ToImageMessage(image, CvTypeToEncoding(image.type()), std::move(header));
}

// ---- msgs::Image -> cv::Mat ----

// Zero-copy view over the message payload. The returned Mat aliases the
// caller's buffer — clone() it if you need to outlive `image`.
inline cv::Mat ToCvMat(const msgs::Image& image) {
  const int cv_type = EncodingToCvType(image.encoding);
  return cv::Mat(static_cast<int>(image.height),
                   static_cast<int>(image.width),
                   cv_type,
                   const_cast<uint8_t*>(image.data.data()),
                   static_cast<size_t>(image.step));
}

// Explicit cv_type override (e.g. for non-standard encodings).
inline cv::Mat ToCvMat(const msgs::Image& image, int cv_type) {
  return cv::Mat(static_cast<int>(image.height),
                   static_cast<int>(image.width),
                   cv_type,
                   const_cast<uint8_t*>(image.data.data()),
                   static_cast<size_t>(image.step));
}

// ---- CompressedImage codecs (PNG / JPEG / ...) ----

// Encode a cv::Mat into a CompressedImage. `format` is e.g. "png", "jpg",
// "webp"; OpenCV imencode does the heavy lifting.
inline msgs::CompressedImage ToCompressedImageMessage(
    const cv::Mat& image,
    const std::string& format = "jpg",
    msgs::Header header = {},
    const std::vector<int>& imencode_params = {}) {
  const std::string extension = (!format.empty() && format.front() == '.')
      ? format : ("." + format);
  std::vector<uint8_t> buffer;
  if (!cv::imencode(extension, image, buffer, imencode_params)) {
    throw std::runtime_error("TalosOS cv_bridge: imencode failed for " + format);
  }

  msgs::CompressedImage msg;
  msg.header = std::move(header);
  // ROS convention: format is e.g. "jpeg" / "png" (no dot). Keep either style
  // benign by stripping the leading dot before storing.
  msg.format = (extension.size() > 1 && extension.front() == '.')
      ? extension.substr(1) : extension;
  msg.data = std::move(buffer);
  return msg;
}

// Decode a CompressedImage back to a cv::Mat (always returns a fresh buffer).
inline cv::Mat ToCvMat(const msgs::CompressedImage& image,
                        int flags = cv::IMREAD_UNCHANGED) {
  return cv::imdecode(image.data, flags);
}

#endif  // TALOSOS_HAVE_OPENCV

}  // namespace talos::adapters

#endif  // TALOSOS_ADAPTERS_OPENCV_H_
