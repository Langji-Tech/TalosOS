#ifndef TALOSOS_MSGS_STD_MSGS_H_
#define TALOSOS_MSGS_STD_MSGS_H_

#include <cstdint>
#include <string>
#include <vector>

#include "talosos/serialization.h"
#include "talosos/time.h"

namespace talos::msgs {

// Equivalent to std_msgs/Header (ROS2 layout: stamp + frame_id).
struct Header {
  Time stamp;
  std::string frame_id;
};

inline void Write(cdr::Writer& w, const Header& h) {
  Write(w, h.stamp);
  cdr::Write(w, h.frame_id);
}
inline void Read(cdr::Reader& r, Header& h) {
  Read(r, h.stamp);
  cdr::Read(r, h.frame_id);
}

struct Empty {};
inline void Write(cdr::Writer& w, const Empty&) {
  // CDR requires at least one byte; ROS2 encodes a single uint8_t structure_needs_at_least_one_member.
  cdr::Write(w, uint8_t{0});
}
inline void Read(cdr::Reader& r, Empty&) {
  uint8_t pad = 0;
  cdr::Read(r, pad);
}

struct String { std::string data; };
inline void Write(cdr::Writer& w, const String& m) { cdr::Write(w, m.data); }
inline void Read(cdr::Reader& r, String& m)        { cdr::Read(r, m.data); }

struct Bool { bool data = false; };
inline void Write(cdr::Writer& w, const Bool& m) { cdr::Write(w, m.data); }
inline void Read(cdr::Reader& r, Bool& m)        { cdr::Read(r, m.data); }

struct Byte { uint8_t data = 0; };
inline void Write(cdr::Writer& w, const Byte& m) { cdr::Write(w, m.data); }
inline void Read(cdr::Reader& r, Byte& m)        { cdr::Read(r, m.data); }

struct Char { int8_t data = 0; };
inline void Write(cdr::Writer& w, const Char& m) { cdr::Write(w, m.data); }
inline void Read(cdr::Reader& r, Char& m)        { cdr::Read(r, m.data); }

struct Int8  { int8_t  data = 0; };
struct Int16 { int16_t data = 0; };
struct Int32 { int32_t data = 0; };
struct Int64 { int64_t data = 0; };
struct UInt8  { uint8_t  data = 0; };
struct UInt16 { uint16_t data = 0; };
struct UInt32 { uint32_t data = 0; };
struct UInt64 { uint64_t data = 0; };
struct Float32 { float  data = 0.f; };
struct Float64 { double data = 0.0; };

inline void Write(cdr::Writer& w, const Int8& m) { cdr::Write(w, m.data); }
inline void Read(cdr::Reader& r, Int8& m)        { cdr::Read(r, m.data); }
inline void Write(cdr::Writer& w, const Int16& m) { cdr::Write(w, m.data); }
inline void Read(cdr::Reader& r, Int16& m)        { cdr::Read(r, m.data); }
inline void Write(cdr::Writer& w, const Int32& m) { cdr::Write(w, m.data); }
inline void Read(cdr::Reader& r, Int32& m)        { cdr::Read(r, m.data); }
inline void Write(cdr::Writer& w, const Int64& m) { cdr::Write(w, m.data); }
inline void Read(cdr::Reader& r, Int64& m)        { cdr::Read(r, m.data); }
inline void Write(cdr::Writer& w, const UInt8& m) { cdr::Write(w, m.data); }
inline void Read(cdr::Reader& r, UInt8& m)        { cdr::Read(r, m.data); }
inline void Write(cdr::Writer& w, const UInt16& m) { cdr::Write(w, m.data); }
inline void Read(cdr::Reader& r, UInt16& m)        { cdr::Read(r, m.data); }
inline void Write(cdr::Writer& w, const UInt32& m) { cdr::Write(w, m.data); }
inline void Read(cdr::Reader& r, UInt32& m)        { cdr::Read(r, m.data); }
inline void Write(cdr::Writer& w, const UInt64& m) { cdr::Write(w, m.data); }
inline void Read(cdr::Reader& r, UInt64& m)        { cdr::Read(r, m.data); }
inline void Write(cdr::Writer& w, const Float32& m) { cdr::Write(w, m.data); }
inline void Read(cdr::Reader& r, Float32& m)        { cdr::Read(r, m.data); }
inline void Write(cdr::Writer& w, const Float64& m) { cdr::Write(w, m.data); }
inline void Read(cdr::Reader& r, Float64& m)        { cdr::Read(r, m.data); }

struct ColorRGBA {
  float r = 0.f, g = 0.f, b = 0.f, a = 1.f;
};
inline void Write(cdr::Writer& w, const ColorRGBA& m) {
  cdr::Write(w, m.r); cdr::Write(w, m.g); cdr::Write(w, m.b); cdr::Write(w, m.a);
}
inline void Read(cdr::Reader& r, ColorRGBA& m) {
  cdr::Read(r, m.r); cdr::Read(r, m.g); cdr::Read(r, m.b); cdr::Read(r, m.a);
}

// ---- MultiArray family ----

struct MultiArrayDimension {
  std::string label;
  uint32_t size = 0;
  uint32_t stride = 0;
};
inline void Write(cdr::Writer& w, const MultiArrayDimension& m) {
  cdr::Write(w, m.label); cdr::Write(w, m.size); cdr::Write(w, m.stride);
}
inline void Read(cdr::Reader& r, MultiArrayDimension& m) {
  cdr::Read(r, m.label); cdr::Read(r, m.size); cdr::Read(r, m.stride);
}

struct MultiArrayLayout {
  std::vector<MultiArrayDimension> dim;
  uint32_t data_offset = 0;
};
inline void Write(cdr::Writer& w, const MultiArrayLayout& m) {
  Write(w, m.dim); cdr::Write(w, m.data_offset);
}
inline void Read(cdr::Reader& r, MultiArrayLayout& m) {
  Read(r, m.dim); cdr::Read(r, m.data_offset);
}

#define TALOSOS_DEFINE_MULTIARRAY(Name, Elem)                   \
  struct Name {                                                  \
    MultiArrayLayout layout;                                     \
    std::vector<Elem> data;                                      \
  };                                                             \
  inline void Write(cdr::Writer& w, const Name& m) {             \
    Write(w, m.layout); Write(w, m.data);                        \
  }                                                              \
  inline void Read(cdr::Reader& r, Name& m) {                    \
    Read(r, m.layout); Read(r, m.data);                          \
  }

TALOSOS_DEFINE_MULTIARRAY(ByteMultiArray,   uint8_t)
TALOSOS_DEFINE_MULTIARRAY(Int8MultiArray,   int8_t)
TALOSOS_DEFINE_MULTIARRAY(Int16MultiArray,  int16_t)
TALOSOS_DEFINE_MULTIARRAY(Int32MultiArray,  int32_t)
TALOSOS_DEFINE_MULTIARRAY(Int64MultiArray,  int64_t)
TALOSOS_DEFINE_MULTIARRAY(UInt8MultiArray,  uint8_t)
TALOSOS_DEFINE_MULTIARRAY(UInt16MultiArray, uint16_t)
TALOSOS_DEFINE_MULTIARRAY(UInt32MultiArray, uint32_t)
TALOSOS_DEFINE_MULTIARRAY(UInt64MultiArray, uint64_t)
TALOSOS_DEFINE_MULTIARRAY(Float32MultiArray, float)
TALOSOS_DEFINE_MULTIARRAY(Float64MultiArray, double)

#undef TALOSOS_DEFINE_MULTIARRAY

}  // namespace talos::msgs

#endif  // TALOSOS_MSGS_STD_MSGS_H_
