#ifndef TALOSOS_MSGS_NAV_MSGS_H_
#define TALOSOS_MSGS_NAV_MSGS_H_

#include <cstdint>
#include <string>
#include <vector>

#include "talosos/msgs/geometry_msgs.h"
#include "talosos/msgs/std_msgs.h"
#include "talosos/serialization.h"
#include "talosos/time.h"

namespace talos::msgs {

struct MapMetaData {
  Time map_load_time;
  float resolution = 0.f;
  uint32_t width = 0;
  uint32_t height = 0;
  Pose origin;
};
inline void Write(cdr::Writer& w, const MapMetaData& m) {
  Write(w, m.map_load_time);
  cdr::Write(w, m.resolution);
  cdr::Write(w, m.width);
  cdr::Write(w, m.height);
  Write(w, m.origin);
}
inline void Read(cdr::Reader& r, MapMetaData& m) {
  Read(r, m.map_load_time);
  cdr::Read(r, m.resolution);
  cdr::Read(r, m.width);
  cdr::Read(r, m.height);
  Read(r, m.origin);
}

struct OccupancyGrid {
  Header header;
  MapMetaData info;
  std::vector<int8_t> data;
};
inline void Write(cdr::Writer& w, const OccupancyGrid& m) {
  Write(w, m.header); Write(w, m.info); Write(w, m.data);
}
inline void Read(cdr::Reader& r, OccupancyGrid& m) {
  Read(r, m.header); Read(r, m.info); Read(r, m.data);
}

struct GridCells {
  Header header;
  float cell_width = 0.f;
  float cell_height = 0.f;
  std::vector<Point> cells;
};
inline void Write(cdr::Writer& w, const GridCells& m) {
  Write(w, m.header);
  cdr::Write(w, m.cell_width);
  cdr::Write(w, m.cell_height);
  Write(w, m.cells);
}
inline void Read(cdr::Reader& r, GridCells& m) {
  Read(r, m.header);
  cdr::Read(r, m.cell_width);
  cdr::Read(r, m.cell_height);
  Read(r, m.cells);
}

struct Path {
  Header header;
  std::vector<PoseStamped> poses;
};
inline void Write(cdr::Writer& w, const Path& m) {
  Write(w, m.header); Write(w, m.poses);
}
inline void Read(cdr::Reader& r, Path& m) {
  Read(r, m.header); Read(r, m.poses);
}

struct Odometry {
  Header header;
  std::string child_frame_id;
  PoseWithCovariance pose;
  TwistWithCovariance twist;
};
inline void Write(cdr::Writer& w, const Odometry& m) {
  Write(w, m.header);
  cdr::Write(w, m.child_frame_id);
  Write(w, m.pose);
  Write(w, m.twist);
}
inline void Read(cdr::Reader& r, Odometry& m) {
  Read(r, m.header);
  cdr::Read(r, m.child_frame_id);
  Read(r, m.pose);
  Read(r, m.twist);
}

}  // namespace talos::msgs

#endif  // TALOSOS_MSGS_NAV_MSGS_H_
