// Smoke test: serialize representative P2 messages and round-trip them through
// CDR, asserting field equality. Exits non-zero on any mismatch.

#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "talosos/messages.h"
#include "talosos/serialization.h"

namespace {

int g_failures = 0;

#define CHECK(cond)                                                 \
  do {                                                              \
    if (!(cond)) {                                                  \
      std::fprintf(stderr, "FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond); \
      ++g_failures;                                                 \
    }                                                               \
  } while (0)

template <typename T>
T RoundTrip(const T& value) {
  auto bytes = talos::cdr::Serialize(value);
  return talos::cdr::Deserialize<T>(bytes.data(), bytes.size());
}

void TestStdMsgs() {
  {
    talos::msgs::String in{"hello"}, out = RoundTrip(in);
    CHECK(out.data == in.data);
  }
  {
    talos::msgs::Int64 in; in.data = -12345678901234LL;
    auto out = RoundTrip(in);
    CHECK(out.data == in.data);
  }
  {
    talos::msgs::Float64MultiArray in;
    in.layout.dim.push_back({"x", 3, 3});
    in.layout.data_offset = 0;
    in.data = {1.0, 2.0, 3.0};
    auto out = RoundTrip(in);
    CHECK(out.layout.dim.size() == 1);
    CHECK(out.layout.dim[0].label == "x");
    CHECK(out.data == in.data);
  }
  {
    talos::msgs::Empty e, out = RoundTrip(e);
    (void)out;
    CHECK(true);
  }
}

void TestGeometry() {
  talos::msgs::PoseWithCovarianceStamped in;
  in.header.stamp = {100, 500'000'000u};
  in.header.frame_id = "odom";
  in.pose.pose.position = {1.0, 2.0, 3.0};
  in.pose.pose.orientation = {0.0, 0.0, 0.0, 1.0};
  for (size_t i = 0; i < in.pose.covariance.size(); ++i) {
    in.pose.covariance[i] = static_cast<double>(i) * 0.1;
  }

  auto out = RoundTrip(in);
  CHECK(out.header.stamp.sec == in.header.stamp.sec);
  CHECK(out.header.stamp.nanosec == in.header.stamp.nanosec);
  CHECK(out.header.frame_id == in.header.frame_id);
  CHECK(out.pose.pose.position.x == in.pose.pose.position.x);
  CHECK(out.pose.pose.orientation.w == in.pose.pose.orientation.w);
  CHECK(out.pose.covariance == in.pose.covariance);

  talos::msgs::TransformStamped tf;
  tf.header.frame_id = "map";
  tf.child_frame_id = "base_link";
  tf.transform.translation = {10.0, 20.0, 30.0};
  tf.transform.rotation = {0.0, 0.0, 0.707, 0.707};
  auto tf_out = RoundTrip(tf);
  CHECK(tf_out.child_frame_id == "base_link");
  CHECK(tf_out.transform.translation.z == 30.0);
}

void TestSensor() {
  talos::msgs::Imu imu;
  imu.header.frame_id = "imu_link";
  imu.orientation.w = 1.0;
  imu.angular_velocity = {0.01, 0.02, 0.03};
  imu.linear_acceleration = {0.0, 0.0, 9.81};
  for (size_t i = 0; i < 9; ++i) imu.orientation_covariance[i] = i * 1e-6;
  auto out = RoundTrip(imu);
  CHECK(out.header.frame_id == "imu_link");
  CHECK(out.angular_velocity.y == 0.02);
  CHECK(out.linear_acceleration.z == 9.81);
  CHECK(out.orientation_covariance == imu.orientation_covariance);

  talos::msgs::Image img;
  img.header.frame_id = "cam";
  img.height = 2; img.width = 3;
  img.encoding = "mono8";
  img.is_bigendian = 0; img.step = 3;
  img.data = {1, 2, 3, 4, 5, 6};
  auto img_out = RoundTrip(img);
  CHECK(img_out.encoding == "mono8");
  CHECK(img_out.step == 3);
  CHECK(img_out.data == img.data);

  talos::msgs::PointCloud2 pc;
  pc.header.frame_id = "lidar";
  pc.height = 1; pc.width = 2;
  talos::msgs::PointField f_x{"x", 0, talos::msgs::PointField::FLOAT32, 1};
  talos::msgs::PointField f_y{"y", 4, talos::msgs::PointField::FLOAT32, 1};
  pc.fields = {f_x, f_y};
  pc.point_step = 8; pc.row_step = 16;
  pc.is_bigendian = false; pc.is_dense = true;
  pc.data.resize(16, 0);
  auto pc_out = RoundTrip(pc);
  CHECK(pc_out.fields.size() == 2);
  CHECK(pc_out.fields[1].name == "y");
  CHECK(pc_out.point_step == 8);

  talos::msgs::LaserScan scan;
  scan.header.frame_id = "base_scan";
  scan.angle_min = -1.57f; scan.angle_max = 1.57f;
  scan.angle_increment = 0.01f;
  scan.range_min = 0.1f; scan.range_max = 30.0f;
  scan.ranges = {1.0f, 2.0f, 3.0f, 4.0f};
  scan.intensities = {10.f, 20.f, 30.f, 40.f};
  auto scan_out = RoundTrip(scan);
  CHECK(scan_out.ranges == scan.ranges);
  CHECK(scan_out.intensities == scan.intensities);

  talos::msgs::JointState js;
  js.name = {"a", "b"};
  js.position = {0.1, 0.2};
  js.velocity = {0.0, 0.0};
  auto js_out = RoundTrip(js);
  CHECK(js_out.name == js.name);
  CHECK(js_out.position == js.position);
  CHECK(js_out.effort.empty());
}

void TestNav() {
  talos::msgs::Odometry odom;
  odom.header.frame_id = "odom";
  odom.child_frame_id = "base_link";
  odom.pose.pose.position = {5.0, 6.0, 0.0};
  odom.twist.twist.linear.x = 0.3;
  auto out = RoundTrip(odom);
  CHECK(out.child_frame_id == "base_link");
  CHECK(out.pose.pose.position.y == 6.0);
  CHECK(out.twist.twist.linear.x == 0.3);

  talos::msgs::OccupancyGrid grid;
  grid.header.frame_id = "map";
  grid.info.resolution = 0.05f;
  grid.info.width = 3; grid.info.height = 2;
  grid.info.map_load_time = {1, 2u};
  grid.data = {0, 50, 100, -1, 0, 100};
  auto grid_out = RoundTrip(grid);
  CHECK(grid_out.info.resolution == 0.05f);
  CHECK(grid_out.info.map_load_time.sec == 1);
  CHECK(grid_out.data == grid.data);

  talos::msgs::Path path;
  path.header.frame_id = "map";
  talos::msgs::PoseStamped ps;
  ps.pose.position.x = 1.0;
  path.poses = {ps, ps, ps};
  auto path_out = RoundTrip(path);
  CHECK(path_out.poses.size() == 3);
}

void TestTfAndViz() {
  talos::msgs::TFMessage tf;
  talos::msgs::TransformStamped ts;
  ts.header.frame_id = "a";
  ts.child_frame_id = "b";
  ts.transform.translation.x = 1.0;
  tf.transforms = {ts};
  auto out = RoundTrip(tf);
  CHECK(out.transforms.size() == 1);
  CHECK(out.transforms[0].child_frame_id == "b");

  talos::msgs::MarkerArray arr;
  talos::msgs::Marker m;
  m.header.frame_id = "map";
  m.ns = "robot";
  m.id = 42;
  m.type = talos::msgs::Marker::CUBE;
  m.action = talos::msgs::Marker::ADD;
  m.scale = {1, 1, 1};
  m.color = {1.f, 0.f, 0.f, 1.f};
  m.points = { {0, 0, 0}, {1, 1, 1} };
  arr.markers = {m};
  auto arr_out = RoundTrip(arr);
  CHECK(arr_out.markers.size() == 1);
  CHECK(arr_out.markers[0].id == 42);
  CHECK(arr_out.markers[0].points.size() == 2);
  CHECK(arr_out.markers[0].color.r == 1.f);
}

void TestPclAndOctomap() {
  talos::msgs::PointIndices indices;
  indices.header.frame_id = "x";
  indices.indices = {1, 2, 3, 4};
  auto out = RoundTrip(indices);
  CHECK(out.indices == indices.indices);

  talos::msgs::Octomap oct;
  oct.header.frame_id = "map";
  oct.binary = true;
  oct.id = "OcTree";
  oct.resolution = 0.1;
  oct.data = {1, 2, 3, 4, 5};
  auto oct_out = RoundTrip(oct);
  CHECK(oct_out.id == "OcTree");
  CHECK(oct_out.resolution == 0.1);
  CHECK(oct_out.binary);
  CHECK(oct_out.data == oct.data);
}

}  // namespace

int main() {
  TestStdMsgs();
  TestGeometry();
  TestSensor();
  TestNav();
  TestTfAndViz();
  TestPclAndOctomap();

  if (g_failures == 0) {
    std::printf("PASS msg_roundtrip (%s)\n", "all groups");
    return 0;
  }
  std::fprintf(stderr, "FAIL %d assertion(s)\n", g_failures);
  return 1;
}
