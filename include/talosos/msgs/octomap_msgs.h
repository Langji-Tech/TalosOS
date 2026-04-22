#ifndef TALOSOS_MSGS_OCTOMAP_MSGS_H_
#define TALOSOS_MSGS_OCTOMAP_MSGS_H_

#include <cstdint>
#include <string>
#include <vector>

#include "talosos/msgs/geometry_msgs.h"
#include "talosos/msgs/std_msgs.h"
#include "talosos/serialization.h"

namespace talos::msgs {

struct Octomap {
  Header header;
  bool binary = false;
  std::string id;
  double resolution = 0.0;
  std::vector<int8_t> data;
};
inline void Write(cdr::Writer& w, const Octomap& m) {
  Write(w, m.header);
  cdr::Write(w, m.binary);
  cdr::Write(w, m.id);
  cdr::Write(w, m.resolution);
  Write(w, m.data);
}
inline void Read(cdr::Reader& r, Octomap& m) {
  Read(r, m.header);
  cdr::Read(r, m.binary);
  cdr::Read(r, m.id);
  cdr::Read(r, m.resolution);
  Read(r, m.data);
}

struct OctomapWithPose {
  Header header;
  Pose origin;
  Octomap octomap;
};
inline void Write(cdr::Writer& w, const OctomapWithPose& m) {
  Write(w, m.header);
  Write(w, m.origin);
  Write(w, m.octomap);
}
inline void Read(cdr::Reader& r, OctomapWithPose& m) {
  Read(r, m.header);
  Read(r, m.origin);
  Read(r, m.octomap);
}

}  // namespace talos::msgs

#endif  // TALOSOS_MSGS_OCTOMAP_MSGS_H_
