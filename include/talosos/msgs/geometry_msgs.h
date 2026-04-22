#ifndef TALOSOS_MSGS_GEOMETRY_MSGS_H_
#define TALOSOS_MSGS_GEOMETRY_MSGS_H_

#include <array>
#include <cstdint>
#include <string>
#include <vector>

#include "talosos/msgs/std_msgs.h"
#include "talosos/serialization.h"

namespace talos::msgs {

// ---- Primitives ----

struct Vector3 { double x = 0, y = 0, z = 0; };
inline void Write(cdr::Writer& w, const Vector3& v) {
  cdr::Write(w, v.x); cdr::Write(w, v.y); cdr::Write(w, v.z);
}
inline void Read(cdr::Reader& r, Vector3& v) {
  cdr::Read(r, v.x); cdr::Read(r, v.y); cdr::Read(r, v.z);
}

struct Point { double x = 0, y = 0, z = 0; };
inline void Write(cdr::Writer& w, const Point& p) {
  cdr::Write(w, p.x); cdr::Write(w, p.y); cdr::Write(w, p.z);
}
inline void Read(cdr::Reader& r, Point& p) {
  cdr::Read(r, p.x); cdr::Read(r, p.y); cdr::Read(r, p.z);
}

struct Point32 { float x = 0.f, y = 0.f, z = 0.f; };
inline void Write(cdr::Writer& w, const Point32& p) {
  cdr::Write(w, p.x); cdr::Write(w, p.y); cdr::Write(w, p.z);
}
inline void Read(cdr::Reader& r, Point32& p) {
  cdr::Read(r, p.x); cdr::Read(r, p.y); cdr::Read(r, p.z);
}

struct Quaternion { double x = 0, y = 0, z = 0, w = 1.0; };
inline void Write(cdr::Writer& wr, const Quaternion& q) {
  cdr::Write(wr, q.x); cdr::Write(wr, q.y); cdr::Write(wr, q.z); cdr::Write(wr, q.w);
}
inline void Read(cdr::Reader& r, Quaternion& q) {
  cdr::Read(r, q.x); cdr::Read(r, q.y); cdr::Read(r, q.z); cdr::Read(r, q.w);
}

struct Pose2D { double x = 0, y = 0, theta = 0; };
inline void Write(cdr::Writer& w, const Pose2D& p) {
  cdr::Write(w, p.x); cdr::Write(w, p.y); cdr::Write(w, p.theta);
}
inline void Read(cdr::Reader& r, Pose2D& p) {
  cdr::Read(r, p.x); cdr::Read(r, p.y); cdr::Read(r, p.theta);
}

// ---- Composite ----

struct Pose { Point position; Quaternion orientation; };
inline void Write(cdr::Writer& w, const Pose& p) {
  Write(w, p.position); Write(w, p.orientation);
}
inline void Read(cdr::Reader& r, Pose& p) {
  Read(r, p.position); Read(r, p.orientation);
}

struct Twist { Vector3 linear; Vector3 angular; };
inline void Write(cdr::Writer& w, const Twist& t) {
  Write(w, t.linear); Write(w, t.angular);
}
inline void Read(cdr::Reader& r, Twist& t) {
  Read(r, t.linear); Read(r, t.angular);
}

struct Accel { Vector3 linear; Vector3 angular; };
inline void Write(cdr::Writer& w, const Accel& a) {
  Write(w, a.linear); Write(w, a.angular);
}
inline void Read(cdr::Reader& r, Accel& a) {
  Read(r, a.linear); Read(r, a.angular);
}

struct Wrench { Vector3 force; Vector3 torque; };
inline void Write(cdr::Writer& w, const Wrench& x) {
  Write(w, x.force); Write(w, x.torque);
}
inline void Read(cdr::Reader& r, Wrench& x) {
  Read(r, x.force); Read(r, x.torque);
}

struct Inertia {
  double m = 0;
  Vector3 com;
  double ixx = 0, ixy = 0, ixz = 0;
  double iyy = 0, iyz = 0;
  double izz = 0;
};
inline void Write(cdr::Writer& w, const Inertia& i) {
  cdr::Write(w, i.m);
  Write(w, i.com);
  cdr::Write(w, i.ixx); cdr::Write(w, i.ixy); cdr::Write(w, i.ixz);
  cdr::Write(w, i.iyy); cdr::Write(w, i.iyz);
  cdr::Write(w, i.izz);
}
inline void Read(cdr::Reader& r, Inertia& i) {
  cdr::Read(r, i.m);
  Read(r, i.com);
  cdr::Read(r, i.ixx); cdr::Read(r, i.ixy); cdr::Read(r, i.ixz);
  cdr::Read(r, i.iyy); cdr::Read(r, i.iyz);
  cdr::Read(r, i.izz);
}

struct Polygon { std::vector<Point32> points; };
inline void Write(cdr::Writer& w, const Polygon& p) { Write(w, p.points); }
inline void Read(cdr::Reader& r, Polygon& p)        { Read(r, p.points); }

struct Transform {
  Vector3 translation;
  Quaternion rotation;
};
inline void Write(cdr::Writer& w, const Transform& t) {
  Write(w, t.translation); Write(w, t.rotation);
}
inline void Read(cdr::Reader& r, Transform& t) {
  Read(r, t.translation); Read(r, t.rotation);
}

// ---- Stamped variants ----

struct PointStamped { Header header; Point point; };
inline void Write(cdr::Writer& w, const PointStamped& m) { Write(w, m.header); Write(w, m.point); }
inline void Read(cdr::Reader& r, PointStamped& m)        { Read(r, m.header); Read(r, m.point); }

struct Vector3Stamped { Header header; Vector3 vector; };
inline void Write(cdr::Writer& w, const Vector3Stamped& m) { Write(w, m.header); Write(w, m.vector); }
inline void Read(cdr::Reader& r, Vector3Stamped& m)        { Read(r, m.header); Read(r, m.vector); }

struct QuaternionStamped { Header header; Quaternion quaternion; };
inline void Write(cdr::Writer& w, const QuaternionStamped& m) { Write(w, m.header); Write(w, m.quaternion); }
inline void Read(cdr::Reader& r, QuaternionStamped& m)        { Read(r, m.header); Read(r, m.quaternion); }

struct PoseStamped { Header header; Pose pose; };
inline void Write(cdr::Writer& w, const PoseStamped& m) { Write(w, m.header); Write(w, m.pose); }
inline void Read(cdr::Reader& r, PoseStamped& m)        { Read(r, m.header); Read(r, m.pose); }

struct TwistStamped { Header header; Twist twist; };
inline void Write(cdr::Writer& w, const TwistStamped& m) { Write(w, m.header); Write(w, m.twist); }
inline void Read(cdr::Reader& r, TwistStamped& m)        { Read(r, m.header); Read(r, m.twist); }

struct AccelStamped { Header header; Accel accel; };
inline void Write(cdr::Writer& w, const AccelStamped& m) { Write(w, m.header); Write(w, m.accel); }
inline void Read(cdr::Reader& r, AccelStamped& m)        { Read(r, m.header); Read(r, m.accel); }

struct WrenchStamped { Header header; Wrench wrench; };
inline void Write(cdr::Writer& w, const WrenchStamped& m) { Write(w, m.header); Write(w, m.wrench); }
inline void Read(cdr::Reader& r, WrenchStamped& m)        { Read(r, m.header); Read(r, m.wrench); }

struct InertiaStamped { Header header; Inertia inertia; };
inline void Write(cdr::Writer& w, const InertiaStamped& m) { Write(w, m.header); Write(w, m.inertia); }
inline void Read(cdr::Reader& r, InertiaStamped& m)        { Read(r, m.header); Read(r, m.inertia); }

struct PolygonStamped { Header header; Polygon polygon; };
inline void Write(cdr::Writer& w, const PolygonStamped& m) { Write(w, m.header); Write(w, m.polygon); }
inline void Read(cdr::Reader& r, PolygonStamped& m)        { Read(r, m.header); Read(r, m.polygon); }

struct TransformStamped {
  Header header;
  std::string child_frame_id;
  Transform transform;
};
inline void Write(cdr::Writer& w, const TransformStamped& t) {
  Write(w, t.header); cdr::Write(w, t.child_frame_id); Write(w, t.transform);
}
inline void Read(cdr::Reader& r, TransformStamped& t) {
  Read(r, t.header); cdr::Read(r, t.child_frame_id); Read(r, t.transform);
}

// ---- With covariance ----

struct PoseWithCovariance {
  Pose pose;
  std::array<double, 36> covariance{};  // row-major 6x6
};
inline void Write(cdr::Writer& w, const PoseWithCovariance& p) {
  Write(w, p.pose); Write(w, p.covariance);
}
inline void Read(cdr::Reader& r, PoseWithCovariance& p) {
  Read(r, p.pose); Read(r, p.covariance);
}

struct PoseWithCovarianceStamped { Header header; PoseWithCovariance pose; };
inline void Write(cdr::Writer& w, const PoseWithCovarianceStamped& m) {
  Write(w, m.header); Write(w, m.pose);
}
inline void Read(cdr::Reader& r, PoseWithCovarianceStamped& m) {
  Read(r, m.header); Read(r, m.pose);
}

struct TwistWithCovariance {
  Twist twist;
  std::array<double, 36> covariance{};
};
inline void Write(cdr::Writer& w, const TwistWithCovariance& p) {
  Write(w, p.twist); Write(w, p.covariance);
}
inline void Read(cdr::Reader& r, TwistWithCovariance& p) {
  Read(r, p.twist); Read(r, p.covariance);
}

struct TwistWithCovarianceStamped { Header header; TwistWithCovariance twist; };
inline void Write(cdr::Writer& w, const TwistWithCovarianceStamped& m) {
  Write(w, m.header); Write(w, m.twist);
}
inline void Read(cdr::Reader& r, TwistWithCovarianceStamped& m) {
  Read(r, m.header); Read(r, m.twist);
}

struct AccelWithCovariance {
  Accel accel;
  std::array<double, 36> covariance{};
};
inline void Write(cdr::Writer& w, const AccelWithCovariance& p) {
  Write(w, p.accel); Write(w, p.covariance);
}
inline void Read(cdr::Reader& r, AccelWithCovariance& p) {
  Read(r, p.accel); Read(r, p.covariance);
}

struct AccelWithCovarianceStamped { Header header; AccelWithCovariance accel; };
inline void Write(cdr::Writer& w, const AccelWithCovarianceStamped& m) {
  Write(w, m.header); Write(w, m.accel);
}
inline void Read(cdr::Reader& r, AccelWithCovarianceStamped& m) {
  Read(r, m.header); Read(r, m.accel);
}

}  // namespace talos::msgs

#endif  // TALOSOS_MSGS_GEOMETRY_MSGS_H_
