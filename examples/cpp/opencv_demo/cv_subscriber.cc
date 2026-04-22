// OpenCV subscriber — receives sensor_msgs::Image, wraps the payload as a
// cv::Mat via the TalosOS cv_bridge adapter, and either shows it with
// cv::imshow (if $DISPLAY is set) or writes the first N frames to /tmp.

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#include <opencv2/opencv.hpp>

#include "talosos/adapters/opencv.h"
#include "talosos/logging.h"
#include "talosos/messages.h"
#include "talosos/node.h"

int main(int argc, char** argv) {
  const int dump_n = (argc > 1) ? std::atoi(argv[1]) : 3;
  const bool has_display = (std::getenv("DISPLAY") != nullptr);

  talos::Init(argc, argv);
  auto node = talos::Node::Create("cv_subscriber");

  int saved = 0;

  auto sub = node->Subscribe<talos::msgs::Image>(
      "/cam/image_raw",
      [&](const talos::msgs::Image& msg) {
        // Zero-copy view — the cv::Mat aliases msg.data until it returns.
        cv::Mat view = talos::adapters::ToCvMat(msg);

        TALOS_LOG(INFO) << "got Image  " << msg.width << "x" << msg.height
                        << "  encoding=" << msg.encoding
                        << "  step=" << msg.step
                        << "  bytes=" << msg.data.size();

        if (has_display) {
          cv::imshow("cv_subscriber", view);
          cv::waitKey(1);                                // non-blocking pump
        } else if (saved < dump_n) {
          char path[64];
          std::snprintf(path, sizeof(path),
                        "/tmp/cv_demo_frame_%d.png", saved);
          cv::imwrite(path, view);                       // clone happens inside
          TALOS_LOG(INFO) << "wrote " << path;
          ++saved;
        }
      });

  // Also subscribe to the compressed variant, for the decode demo.
  auto sub_c = node->Subscribe<talos::msgs::CompressedImage>(
      "/cam/image/compressed",
      [&](const talos::msgs::CompressedImage& msg) {
        cv::Mat mat = talos::adapters::ToCvMat(msg);     // imdecode
        TALOS_LOG(INFO) << "got CompressedImage format=" << msg.format
                        << "  decoded=" << mat.cols << "x" << mat.rows;
        if (!has_display && saved < dump_n) {
          char path[64];
          std::snprintf(path, sizeof(path),
                        "/tmp/cv_demo_decoded_%d.jpg", saved);
          cv::imwrite(path, mat);
        }
      });

  TALOS_LOG(INFO) << "subscribed  raw=/cam/image_raw  compressed=/cam/image/compressed"
                  << "  display=" << (has_display ? "on" : "off (files -> /tmp/)");
  node->Spin();
  return 0;
}
