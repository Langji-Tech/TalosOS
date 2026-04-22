#ifndef TALOSOS_TIME_H_
#define TALOSOS_TIME_H_

#include <cstdint>

#include "talosos/serialization.h"

namespace talos {

// ROS-compatible timestamp. `sec` may be negative for pre-epoch stamps;
// `nanosec` is always [0, 1e9).
struct Time {
  int32_t sec = 0;
  uint32_t nanosec = 0;

  static Time Now();
  double seconds() const;
  bool operator==(const Time& o) const { return sec == o.sec && nanosec == o.nanosec; }
  bool operator!=(const Time& o) const { return !(*this == o); }
};

inline void Write(cdr::Writer& w, const Time& t) {
  cdr::Write(w, t.sec);
  cdr::Write(w, t.nanosec);
}
inline void Read(cdr::Reader& r, Time& t) {
  cdr::Read(r, t.sec);
  cdr::Read(r, t.nanosec);
}

struct Duration {
  int32_t sec = 0;
  int32_t nanosec = 0;
  bool operator==(const Duration& o) const { return sec == o.sec && nanosec == o.nanosec; }
};

inline void Write(cdr::Writer& w, const Duration& d) {
  cdr::Write(w, d.sec);
  cdr::Write(w, d.nanosec);
}
inline void Read(cdr::Reader& r, Duration& d) {
  cdr::Read(r, d.sec);
  cdr::Read(r, d.nanosec);
}

}  // namespace talos

#endif  // TALOSOS_TIME_H_
