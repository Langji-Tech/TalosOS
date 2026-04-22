#ifndef TALOSOS_MSGS_PCL_MSGS_H_
#define TALOSOS_MSGS_PCL_MSGS_H_

#include <cstdint>
#include <vector>

#include "talosos/msgs/sensor_msgs.h"
#include "talosos/msgs/std_msgs.h"
#include "talosos/serialization.h"

namespace talos::msgs {

struct PointIndices {
  Header header;
  std::vector<int32_t> indices;
};
inline void Write(cdr::Writer& w, const PointIndices& m) {
  Write(w, m.header); Write(w, m.indices);
}
inline void Read(cdr::Reader& r, PointIndices& m) {
  Read(r, m.header); Read(r, m.indices);
}

struct ModelCoefficients {
  Header header;
  std::vector<float> values;
};
inline void Write(cdr::Writer& w, const ModelCoefficients& m) {
  Write(w, m.header); Write(w, m.values);
}
inline void Read(cdr::Reader& r, ModelCoefficients& m) {
  Read(r, m.header); Read(r, m.values);
}

struct Vertices {
  std::vector<uint32_t> vertices;
};
inline void Write(cdr::Writer& w, const Vertices& m) { Write(w, m.vertices); }
inline void Read(cdr::Reader& r, Vertices& m)        { Read(r, m.vertices); }

struct PolygonMesh {
  Header header;
  PointCloud2 cloud;
  std::vector<Vertices> polygons;
};
inline void Write(cdr::Writer& w, const PolygonMesh& m) {
  Write(w, m.header);
  Write(w, m.cloud);
  Write(w, m.polygons);
}
inline void Read(cdr::Reader& r, PolygonMesh& m) {
  Read(r, m.header);
  Read(r, m.cloud);
  Read(r, m.polygons);
}

}  // namespace talos::msgs

#endif  // TALOSOS_MSGS_PCL_MSGS_H_
