#ifndef TALOSOS_ADAPTERS_EIGEN_H_
#define TALOSOS_ADAPTERS_EIGEN_H_

#include <utility>

#if __has_include(<Eigen/Geometry>)
#include <Eigen/Geometry>
#endif

#include "talosos/messages.h"

namespace talos::adapters {

#if __has_include(<Eigen/Geometry>)

inline Eigen::Isometry3d ToIsometry(const msgs::Pose& pose) {
  Eigen::Quaterniond quaternion(
      pose.orientation.w, pose.orientation.x, pose.orientation.y, pose.orientation.z);
  Eigen::Isometry3d transform = Eigen::Isometry3d::Identity();
  transform.linear() = quaternion.normalized().toRotationMatrix();
  transform.translation() = Eigen::Vector3d(
      pose.position.x, pose.position.y, pose.position.z);
  return transform;
}

inline msgs::Pose ToPoseMessage(const Eigen::Isometry3d& transform) {
  const Eigen::Quaterniond quaternion(transform.linear());

  msgs::Pose pose;
  pose.position.x = transform.translation().x();
  pose.position.y = transform.translation().y();
  pose.position.z = transform.translation().z();
  pose.orientation.x = quaternion.x();
  pose.orientation.y = quaternion.y();
  pose.orientation.z = quaternion.z();
  pose.orientation.w = quaternion.w();
  return pose;
}

inline msgs::PoseStamped ToPoseStamped(const Eigen::Isometry3d& transform,
                                        msgs::Header header = {}) {
  msgs::PoseStamped stamped;
  stamped.header = std::move(header);
  stamped.pose = ToPoseMessage(transform);
  return stamped;
}

inline Eigen::Isometry3d ToIsometry(const msgs::PoseStamped& stamped) {
  return ToIsometry(stamped.pose);
}

#endif

}  // namespace talos::adapters

#endif  // TALOSOS_ADAPTERS_EIGEN_H_
