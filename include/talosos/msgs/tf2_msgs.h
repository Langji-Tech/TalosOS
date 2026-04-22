#ifndef TALOSOS_MSGS_TF2_MSGS_H_
#define TALOSOS_MSGS_TF2_MSGS_H_

#include <vector>

#include "talosos/msgs/geometry_msgs.h"
#include "talosos/serialization.h"

namespace talos::msgs {

struct TFMessage {
  std::vector<TransformStamped> transforms;
};
inline void Write(cdr::Writer& w, const TFMessage& m) { Write(w, m.transforms); }
inline void Read(cdr::Reader& r, TFMessage& m)        { Read(r, m.transforms); }

}  // namespace talos::msgs

#endif  // TALOSOS_MSGS_TF2_MSGS_H_
