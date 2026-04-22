#ifndef TALOSOS_MSGS_VISUALIZATION_MSGS_H_
#define TALOSOS_MSGS_VISUALIZATION_MSGS_H_

#include <cstdint>
#include <string>
#include <vector>

#include "talosos/msgs/geometry_msgs.h"
#include "talosos/msgs/std_msgs.h"
#include "talosos/serialization.h"
#include "talosos/time.h"

namespace talos::msgs {

struct Marker {
  // Type constants.
  static constexpr int32_t ARROW            = 0;
  static constexpr int32_t CUBE             = 1;
  static constexpr int32_t SPHERE           = 2;
  static constexpr int32_t CYLINDER         = 3;
  static constexpr int32_t LINE_STRIP       = 4;
  static constexpr int32_t LINE_LIST        = 5;
  static constexpr int32_t CUBE_LIST        = 6;
  static constexpr int32_t SPHERE_LIST      = 7;
  static constexpr int32_t POINTS           = 8;
  static constexpr int32_t TEXT_VIEW_FACING = 9;
  static constexpr int32_t MESH_RESOURCE    = 10;
  static constexpr int32_t TRIANGLE_LIST    = 11;

  // Action constants.
  static constexpr int32_t ADD            = 0;
  static constexpr int32_t MODIFY         = 0;
  static constexpr int32_t DELETE         = 2;
  static constexpr int32_t DELETEALL      = 3;

  Header header;
  std::string ns;
  int32_t id = 0;
  int32_t type = 0;
  int32_t action = ADD;
  Pose pose;
  Vector3 scale;
  ColorRGBA color;
  Duration lifetime;
  bool frame_locked = false;
  std::vector<Point> points;
  std::vector<ColorRGBA> colors;
  std::string text;
  std::string mesh_resource;
  bool mesh_use_embedded_materials = false;
};
inline void Write(cdr::Writer& w, const Marker& m) {
  Write(w, m.header);
  cdr::Write(w, m.ns);
  cdr::Write(w, m.id);
  cdr::Write(w, m.type);
  cdr::Write(w, m.action);
  Write(w, m.pose);
  Write(w, m.scale);
  Write(w, m.color);
  Write(w, m.lifetime);
  cdr::Write(w, m.frame_locked);
  Write(w, m.points);
  Write(w, m.colors);
  cdr::Write(w, m.text);
  cdr::Write(w, m.mesh_resource);
  cdr::Write(w, m.mesh_use_embedded_materials);
}
inline void Read(cdr::Reader& r, Marker& m) {
  Read(r, m.header);
  cdr::Read(r, m.ns);
  cdr::Read(r, m.id);
  cdr::Read(r, m.type);
  cdr::Read(r, m.action);
  Read(r, m.pose);
  Read(r, m.scale);
  Read(r, m.color);
  Read(r, m.lifetime);
  cdr::Read(r, m.frame_locked);
  Read(r, m.points);
  Read(r, m.colors);
  cdr::Read(r, m.text);
  cdr::Read(r, m.mesh_resource);
  cdr::Read(r, m.mesh_use_embedded_materials);
}

struct MarkerArray { std::vector<Marker> markers; };
inline void Write(cdr::Writer& w, const MarkerArray& m) { Write(w, m.markers); }
inline void Read(cdr::Reader& r, MarkerArray& m)        { Read(r, m.markers); }

struct ImageMarker {
  static constexpr int32_t CIRCLE     = 0;
  static constexpr int32_t LINE_STRIP = 1;
  static constexpr int32_t LINE_LIST  = 2;
  static constexpr int32_t POLYGON    = 3;
  static constexpr int32_t POINTS     = 4;

  static constexpr int32_t ADD    = 0;
  static constexpr int32_t REMOVE = 1;

  Header header;
  std::string ns;
  int32_t id = 0;
  int32_t type = 0;
  int32_t action = ADD;
  Point position;
  float scale = 1.f;
  ColorRGBA outline_color;
  uint8_t filled = 0;
  ColorRGBA fill_color;
  Duration lifetime;
  std::vector<Point> points;
  std::vector<ColorRGBA> outline_colors;
};
inline void Write(cdr::Writer& w, const ImageMarker& m) {
  Write(w, m.header);
  cdr::Write(w, m.ns);
  cdr::Write(w, m.id);
  cdr::Write(w, m.type);
  cdr::Write(w, m.action);
  Write(w, m.position);
  cdr::Write(w, m.scale);
  Write(w, m.outline_color);
  cdr::Write(w, m.filled);
  Write(w, m.fill_color);
  Write(w, m.lifetime);
  Write(w, m.points);
  Write(w, m.outline_colors);
}
inline void Read(cdr::Reader& r, ImageMarker& m) {
  Read(r, m.header);
  cdr::Read(r, m.ns);
  cdr::Read(r, m.id);
  cdr::Read(r, m.type);
  cdr::Read(r, m.action);
  Read(r, m.position);
  cdr::Read(r, m.scale);
  Read(r, m.outline_color);
  cdr::Read(r, m.filled);
  Read(r, m.fill_color);
  Read(r, m.lifetime);
  Read(r, m.points);
  Read(r, m.outline_colors);
}

struct MenuEntry {
  static constexpr uint8_t FEEDBACK        = 0;
  static constexpr uint8_t ROSRUN          = 1;
  static constexpr uint8_t ROSLAUNCH       = 2;

  uint32_t id = 0;
  uint32_t parent_id = 0;
  std::string title;
  std::string command;
  uint8_t command_type = FEEDBACK;
};
inline void Write(cdr::Writer& w, const MenuEntry& m) {
  cdr::Write(w, m.id);
  cdr::Write(w, m.parent_id);
  cdr::Write(w, m.title);
  cdr::Write(w, m.command);
  cdr::Write(w, m.command_type);
}
inline void Read(cdr::Reader& r, MenuEntry& m) {
  cdr::Read(r, m.id);
  cdr::Read(r, m.parent_id);
  cdr::Read(r, m.title);
  cdr::Read(r, m.command);
  cdr::Read(r, m.command_type);
}

}  // namespace talos::msgs

#endif  // TALOSOS_MSGS_VISUALIZATION_MSGS_H_
