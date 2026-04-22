// OpenCV publisher — loads a file with cv::imread, publishes as a raw
// sensor_msgs::Image (bgr8 / mono8 auto-detected) on /cam/image_raw.
// Also (optionally) publishes a compressed JPEG on /cam/image/compressed
// via ToCompressedImageMessage for comparison.

#include <chrono>
#include <cstdlib>
#include <string>
#include <thread>

#include <opencv2/opencv.hpp>

#include "talosos/adapters/opencv.h"
#include "talosos/logging.h"
#include "talosos/messages.h"
#include "talosos/node.h"

int main(int argc, char** argv) {
  const std::string path = (argc > 1)
      ? argv[1] : "/home/ubuntu24/Software/TalosOS/image.png";
  const double hz = (argc > 2) ? std::atof(argv[2]) : 5.0;
  const bool color = (argc <= 3 || std::string(argv[3]) != "mono");

  talos::Init(argc, argv);
  auto node = talos::Node::Create("cv_publisher");

  // Load once; cv::imread returns BGR by default for IMREAD_COLOR.
  cv::Mat mat = cv::imread(
      path, color ? cv::IMREAD_COLOR : cv::IMREAD_GRAYSCALE);
  if (mat.empty()) {
    TALOS_LOG(FATAL) << "cannot open " << path;
    return 2;
  }
  TALOS_LOG(INFO) << "loaded " << path
                  << "  cols=" << mat.cols << "  rows=" << mat.rows
                  << "  type=" << mat.type()
                  << "  encoding=" << talos::adapters::CvTypeToEncoding(mat.type());

  auto pub_raw  = node->Advertise<talos::msgs::Image>("/cam/image_raw");
  auto pub_jpeg = node->Advertise<talos::msgs::CompressedImage>(
      "/cam/image/compressed");

  using namespace std::chrono_literals;
  const auto period = std::chrono::microseconds(
      static_cast<long long>(1e6 / hz));
  int frame = 0;
  while (talos::Ok()) {
    talos::msgs::Header header;
    header.stamp = talos::Time::Now();
    header.frame_id = "cam";

    // Raw: mat -> sensor_msgs/Image (copy payload, no recompress).
    auto raw = talos::adapters::ToImageMessage(mat, header);

    // Compressed: mat -> JPEG (configurable quality).
    auto jpeg = talos::adapters::ToCompressedImageMessage(
        mat, "jpg", header, {cv::IMWRITE_JPEG_QUALITY, 85});

    pub_raw.Publish(raw);
    pub_jpeg.Publish(jpeg);

    if ((frame++ % 20) == 0) {
      TALOS_LOG(INFO) << "frame " << (frame - 1)
                      << "  raw=" << raw.data.size() << "B"
                      << "  jpeg=" << jpeg.data.size() << "B";
    }
    std::this_thread::sleep_for(period);
  }
  return 0;
}
