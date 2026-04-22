#ifndef TALOSOS_ADAPTERS_PCL_H_
#define TALOSOS_ADAPTERS_PCL_H_

#include <cstdint>
#include <cstring>
#include <utility>

#if __has_include(<pcl/point_cloud.h>) && __has_include(<pcl/point_types.h>)
#include <pcl/point_cloud.h>
#include <pcl/point_types.h>
#endif

#include "talosos/messages.h"

namespace talos::adapters {

#if __has_include(<pcl/point_cloud.h>) && __has_include(<pcl/point_types.h>)
inline msgs::PointCloud ToPointCloudMessage(
    const pcl::PointCloud<pcl::PointXYZ>& cloud,
    msgs::Header header = {}) {
  msgs::PointCloud msg;
  msg.header = std::move(header);
  msg.width = cloud.width;
  msg.height = cloud.height;
  msg.is_dense = cloud.is_dense;
  msg.point_step = static_cast<uint32_t>(sizeof(pcl::PointXYZ));
  msg.row_step = msg.point_step * msg.width;
  msg.fields = {
      {.name = "x", .offset = 0U, .datatype = 7U, .count = 1U},
      {.name = "y", .offset = 4U, .datatype = 7U, .count = 1U},
      {.name = "z", .offset = 8U, .datatype = 7U, .count = 1U},
  };
  msg.data.resize(cloud.points.size() * sizeof(pcl::PointXYZ));
  std::memcpy(msg.data.data(), cloud.points.data(), msg.data.size());
  return msg;
}

inline pcl::PointCloud<pcl::PointXYZ> ToPclPointCloud(const msgs::PointCloud& cloud) {
  pcl::PointCloud<pcl::PointXYZ> output;
  output.width = cloud.width;
  output.height = cloud.height;
  output.is_dense = cloud.is_dense;
  output.points.resize(cloud.data.size() / sizeof(pcl::PointXYZ));
  std::memcpy(output.points.data(), cloud.data.data(), cloud.data.size());
  return output;
}
#endif

}

#endif
