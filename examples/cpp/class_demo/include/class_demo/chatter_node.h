#ifndef CLASS_DEMO_CHATTER_NODE_H_
#define CLASS_DEMO_CHATTER_NODE_H_

// Class-form example: how to own a talos::Node + its publishers / subscriptions
// / services as members of a regular C++ class, with callbacks implemented as
// methods. This is the pattern most production nodes use (rclcpp::Node users
// will recognize it).

#include <atomic>
#include <memory>
#include <string>
#include <thread>

#include "talosos/messages.h"
#include "talosos/node.h"
#include "talosos/service.h"
#include "talosos/serialization.h"

namespace class_demo {

// Service response message — declared inline via TALOS_MESSAGE_FIELDS.
// Request is std_msgs/Empty (one pad byte on the wire).
struct GetCountResponse {
  int64_t count = 0;
  TALOS_MESSAGE_FIELDS(count)
};

class ChatterNode {
 public:
  ChatterNode(std::shared_ptr<talos::Node> node, double publish_hz = 2.0);
  ~ChatterNode();

  // Non-copyable, non-movable — holds threads and zenoh handles.
  ChatterNode(const ChatterNode&) = delete;
  ChatterNode& operator=(const ChatterNode&) = delete;

  void Start();   // launches the periodic publisher thread
  void Stop();    // joins it

  int64_t count() const { return count_.load(); }

 private:
  // --- Callbacks ---
  void OnReset(const talos::msgs::Empty& msg);
  GetCountResponse OnGetCount(const talos::msgs::Empty& req);

  // --- Worker ---
  void PublishLoop();

  // --- State ---
  std::shared_ptr<talos::Node> node_;
  double publish_hz_;

  // ROS1-style: type-erased handles; the message type only appears at the
  // Advertise<T>() / Subscribe<T>() / AdvertiseService<Req,Resp>() call site.
  talos::Publisher    chatter_pub_;
  talos::Subscription reset_sub_;
  talos::Service      count_svc_;

  std::atomic<int64_t> count_{0};
  std::atomic<bool> running_{false};
  std::thread worker_;
};

}  // namespace class_demo

#endif  // CLASS_DEMO_CHATTER_NODE_H_
