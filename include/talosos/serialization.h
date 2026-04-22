#ifndef TALOSOS_SERIALIZATION_H_
#define TALOSOS_SERIALIZATION_H_

#include <array>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <string_view>
#include <tuple>
#include <type_traits>
#include <utility>
#include <vector>

namespace talos::cdr {

// CDR encapsulation constants. We always emit little-endian CDR
// (representation_id 0x00 0x01, options 0x00 0x00).
inline constexpr size_t kEncapsulationHeaderSize = 4;
inline constexpr uint8_t kCdrLeHeader[4] = {0x00, 0x01, 0x00, 0x00};

class Writer {
 public:
  Writer() {
    buf_.reserve(64);
    buf_.insert(buf_.end(), std::begin(kCdrLeHeader), std::end(kCdrLeHeader));
  }

  void WriteU8(uint8_t v)  { buf_.push_back(v); }
  void WriteI8(int8_t v)   { WriteU8(static_cast<uint8_t>(v)); }
  void WriteBool(bool v)   { WriteU8(v ? 1 : 0); }

  void WriteU16(uint16_t v) {
    Align(2);
    buf_.push_back(static_cast<uint8_t>(v & 0xFFu));
    buf_.push_back(static_cast<uint8_t>((v >> 8) & 0xFFu));
  }
  void WriteI16(int16_t v) { WriteU16(static_cast<uint16_t>(v)); }

  void WriteU32(uint32_t v) {
    Align(4);
    for (int i = 0; i < 4; ++i) {
      buf_.push_back(static_cast<uint8_t>((v >> (i * 8)) & 0xFFu));
    }
  }
  void WriteI32(int32_t v) { WriteU32(static_cast<uint32_t>(v)); }

  void WriteU64(uint64_t v) {
    Align(8);
    for (int i = 0; i < 8; ++i) {
      buf_.push_back(static_cast<uint8_t>((v >> (i * 8)) & 0xFFu));
    }
  }
  void WriteI64(int64_t v) { WriteU64(static_cast<uint64_t>(v)); }

  void WriteF32(float v) {
    uint32_t bits;
    std::memcpy(&bits, &v, 4);
    WriteU32(bits);
  }

  void WriteF64(double v) {
    uint64_t bits;
    std::memcpy(&bits, &v, 8);
    WriteU64(bits);
  }

  void WriteString(std::string_view s) {
    const uint32_t n = static_cast<uint32_t>(s.size()) + 1;
    WriteU32(n);
    buf_.insert(buf_.end(), s.begin(), s.end());
    buf_.push_back(0);
  }

  void WriteRawBytes(const uint8_t* data, size_t len) {
    buf_.insert(buf_.end(), data, data + len);
  }

  size_t size() const { return buf_.size(); }
  const uint8_t* data() const { return buf_.data(); }
  const std::vector<uint8_t>& buffer() const { return buf_; }
  std::vector<uint8_t> Release() && { return std::move(buf_); }

 private:
  void Align(size_t n) {
    const size_t body = buf_.size() - kEncapsulationHeaderSize;
    const size_t pad = (n - (body % n)) % n;
    for (size_t i = 0; i < pad; ++i) buf_.push_back(0);
  }

  std::vector<uint8_t> buf_;
};

class Reader {
 public:
  Reader(const uint8_t* data, size_t len)
      : data_(data), len_(len), pos_(kEncapsulationHeaderSize) {
    if (len < kEncapsulationHeaderSize) {
      throw std::runtime_error("CDR buffer too small for encapsulation header");
    }
  }

  uint8_t  ReadU8()   { EnsureAvail(1); return data_[pos_++]; }
  int8_t   ReadI8()   { return static_cast<int8_t>(ReadU8()); }
  bool     ReadBool() { return ReadU8() != 0; }

  uint16_t ReadU16() {
    Align(2); EnsureAvail(2);
    uint16_t v = static_cast<uint16_t>(data_[pos_])
               | (static_cast<uint16_t>(data_[pos_ + 1]) << 8);
    pos_ += 2;
    return v;
  }
  int16_t ReadI16() { return static_cast<int16_t>(ReadU16()); }

  uint32_t ReadU32() {
    Align(4); EnsureAvail(4);
    uint32_t v = 0;
    for (int i = 0; i < 4; ++i) {
      v |= static_cast<uint32_t>(data_[pos_ + i]) << (i * 8);
    }
    pos_ += 4;
    return v;
  }
  int32_t ReadI32() { return static_cast<int32_t>(ReadU32()); }

  uint64_t ReadU64() {
    Align(8); EnsureAvail(8);
    uint64_t v = 0;
    for (int i = 0; i < 8; ++i) {
      v |= static_cast<uint64_t>(data_[pos_ + i]) << (i * 8);
    }
    pos_ += 8;
    return v;
  }
  int64_t ReadI64() { return static_cast<int64_t>(ReadU64()); }

  float ReadF32() {
    uint32_t bits = ReadU32();
    float v;
    std::memcpy(&v, &bits, 4);
    return v;
  }
  double ReadF64() {
    uint64_t bits = ReadU64();
    double v;
    std::memcpy(&v, &bits, 8);
    return v;
  }

  std::string ReadString() {
    const uint32_t n = ReadU32();
    if (n == 0) return {};
    EnsureAvail(n);
    const size_t payload = (n >= 1) ? (n - 1) : 0;
    std::string s(reinterpret_cast<const char*>(data_ + pos_), payload);
    pos_ += n;
    return s;
  }

  size_t remaining() const { return len_ - pos_; }

 private:
  void Align(size_t n) {
    const size_t body = pos_ - kEncapsulationHeaderSize;
    const size_t pad = (n - (body % n)) % n;
    pos_ += pad;
  }
  void EnsureAvail(size_t n) const {
    if (pos_ + n > len_) {
      throw std::runtime_error("CDR buffer underrun");
    }
  }

  const uint8_t* data_;
  size_t len_;
  size_t pos_;
};

// ---- Primitive free-function overloads ----

inline void Write(Writer& w, bool v)     { w.WriteBool(v); }
inline void Write(Writer& w, uint8_t v)  { w.WriteU8(v); }
inline void Write(Writer& w, int8_t v)   { w.WriteI8(v); }
inline void Write(Writer& w, uint16_t v) { w.WriteU16(v); }
inline void Write(Writer& w, int16_t v)  { w.WriteI16(v); }
inline void Write(Writer& w, uint32_t v) { w.WriteU32(v); }
inline void Write(Writer& w, int32_t v)  { w.WriteI32(v); }
inline void Write(Writer& w, uint64_t v) { w.WriteU64(v); }
inline void Write(Writer& w, int64_t v)  { w.WriteI64(v); }
inline void Write(Writer& w, float v)    { w.WriteF32(v); }
inline void Write(Writer& w, double v)   { w.WriteF64(v); }
inline void Write(Writer& w, std::string_view v) { w.WriteString(v); }
inline void Write(Writer& w, const std::string& v) { w.WriteString(v); }
inline void Write(Writer& w, const char* v) {
  w.WriteString(v ? std::string_view(v) : std::string_view());
}

inline void Read(Reader& r, bool& v)     { v = r.ReadBool(); }
inline void Read(Reader& r, uint8_t& v)  { v = r.ReadU8(); }
inline void Read(Reader& r, int8_t& v)   { v = r.ReadI8(); }
inline void Read(Reader& r, uint16_t& v) { v = r.ReadU16(); }
inline void Read(Reader& r, int16_t& v)  { v = r.ReadI16(); }
inline void Read(Reader& r, uint32_t& v) { v = r.ReadU32(); }
inline void Read(Reader& r, int32_t& v)  { v = r.ReadI32(); }
inline void Read(Reader& r, uint64_t& v) { v = r.ReadU64(); }
inline void Read(Reader& r, int64_t& v)  { v = r.ReadI64(); }
inline void Read(Reader& r, float& v)    { v = r.ReadF32(); }
inline void Read(Reader& r, double& v)   { v = r.ReadF64(); }
inline void Read(Reader& r, std::string& v) { v = r.ReadString(); }

// Vector as CDR sequence: uint32 length + elements.
template <typename T, typename A>
void Write(Writer& w, const std::vector<T, A>& v) {
  w.WriteU32(static_cast<uint32_t>(v.size()));
  for (const auto& e : v) {
    Write(w, e);
  }
}

template <typename T, typename A>
void Read(Reader& r, std::vector<T, A>& v) {
  const uint32_t n = r.ReadU32();
  v.clear();
  v.resize(n);
  for (uint32_t i = 0; i < n; ++i) {
    Read(r, v[i]);
  }
}

// Fixed-size std::array: elements are written without a length prefix.
template <typename T, size_t N>
void Write(Writer& w, const std::array<T, N>& v) {
  for (const auto& e : v) Write(w, e);
}

template <typename T, size_t N>
void Read(Reader& r, std::array<T, N>& v) {
  for (auto& e : v) Read(r, e);
}

// ---- Reflection-lite: structs exposing talosos_fields() serialize automatically ----
//
// A user struct can opt into automatic CDR serialization by adding the
// TALOS_MESSAGE_FIELDS(field1, field2, ...) macro inside the struct body.
// The macro generates const/non-const talosos_fields() tuples of references;
// the templates below unpack them and recurse via unqualified Write/Read so
// nested custom types and hand-written overloads both compose via ADL.

template <typename T, typename = void>
struct has_talosos_fields : std::false_type {};

template <typename T>
struct has_talosos_fields<
    T, std::void_t<decltype(std::declval<const T&>().talosos_fields())>>
    : std::true_type {};

template <typename T>
std::enable_if_t<has_talosos_fields<T>::value>
Write(Writer& w, const T& value) {
  std::apply(
      [&](const auto&... fields) { (Write(w, fields), ...); },
      value.talosos_fields());
}

template <typename T>
std::enable_if_t<has_talosos_fields<T>::value>
Read(Reader& r, T& value) {
  std::apply(
      [&](auto&... fields) { (Read(r, fields), ...); },
      value.talosos_fields());
}

// Convenience: serialize a whole value to a fresh buffer.
template <typename T>
std::vector<uint8_t> Serialize(const T& value) {
  Writer w;
  Write(w, value);
  return std::move(w).Release();
}

template <typename T>
T Deserialize(const uint8_t* data, size_t len) {
  Reader r(data, len);
  T value{};
  Read(r, value);
  return value;
}

}  // namespace talos::cdr

// Opt-in reflection macro. Place inside a struct body:
//
//   struct MyMsg {
//     std::string name;
//     talos::msgs::Header header;
//     int32_t value;
//     TALOS_MESSAGE_FIELDS(name, header, value)
//   };
//
// The macro generates two talosos_fields() accessors (const and mutable) that
// return std::tie over the listed members. Serialization is then automatic.
// The fields are serialized in the listed order, so the order here IS the CDR
// wire layout — it must match any peer (other language binding, ros2 msg,
// etc.) that you want to interoperate with.
#define TALOS_MESSAGE_FIELDS(...)                           \
  auto talosos_fields() const { return std::tie(__VA_ARGS__); } \
  auto talosos_fields() { return std::tie(__VA_ARGS__); }

#endif  // TALOSOS_SERIALIZATION_H_