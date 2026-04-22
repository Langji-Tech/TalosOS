#include "class_demo/chatter_node.h"

#include <chrono>
#include <functional>

#include "talosos/logging.h"

namespace class_demo {

ChatterNode::ChatterNode(std::shared_ptr<talos::Node> node, double publish_hz)
    : node_(std::move(node)),
      publish_hz_(publish_hz) {
  // Publishers and subscriptions are created in the constructor so they are
  // ready before Start(). The zenoh sessions are already live by the time
  // Node::Create returned.
  chatter_pub_ = node_->Advertise<talos::msgs::Int64>("chatter");

  // Subscribe / AdvertiseService accept any of:
  //   (a) member-function pointer  — most concise, ROS1 style
  //   (b) lambda with `this` capture
  //   (c) std::bind / std::function for free/bound callables
  //
  // (a) is used here; (b) and (c) are shown below for reference.
  reset_sub_ = node_->Subscribe("reset", &ChatterNode::OnReset, this);
  count_svc_ = node_->AdvertiseService<talos::msgs::Empty, GetCountResponse>(
      "get_count", &ChatterNode::OnGetCount, this);

  // --- equivalent alternative styles (commented) ---
  //
  // (b) lambda:
  //   reset_sub_ = node_->Subscribe<talos::msgs::Empty>(
  //       "reset", [this](const talos::msgs::Empty& m) { OnReset(m); });
  //
  // (c) std::bind (legacy but occasionally useful for pre-bound args):
  //   reset_sub_ = node_->Subscribe<talos::msgs::Empty>(
  //       "reset", std::bind(&ChatterNode::OnReset, this,
  //                          std::placeholders::_1));

  // iostream-style logging — same helpers as glog / ROS1:
  //     TALOS_LOG(INFO) << ...            // glog / absl style
  //     TALOS_INFO_STREAM("foo=" << x)    // ROS1 style
  //     TALOS_INFO("foo=%d", x)           // printf style
  TALOS_LOG(INFO) << "ChatterNode ready"
                  << "  publish=/"  << chatter_pub_.key()
                  << "  subscribe=/" << reset_sub_.key()
                  << "  service=/"   << count_svc_.key();
}

ChatterNode::~ChatterNode() { Stop(); }

void ChatterNode::Start() {
  if (running_.exchange(true)) return;
  worker_ = std::thread(&ChatterNode::PublishLoop, this);
}

void ChatterNode::Stop() {
  if (!running_.exchange(false)) return;
  if (worker_.joinable()) worker_.join();
}

void ChatterNode::OnReset(const talos::msgs::Empty& /*msg*/) {
  const int64_t prev = count_.exchange(0);
  TALOS_LOG(INFO) << "reset received: count was " << prev;
}

GetCountResponse ChatterNode::OnGetCount(const talos::msgs::Empty& /*req*/) {
  GetCountResponse resp;
  resp.count = count_.load();
  TALOS_LOG(DEBUG) << "get_count -> " << resp.count;
  return resp;
}

void ChatterNode::PublishLoop() {
  const auto period = std::chrono::microseconds(
      static_cast<long long>(1'000'000.0 / publish_hz_));
  while (running_.load() && talos::Ok()) {
    talos::msgs::Int64 msg;
    msg.data = count_.fetch_add(1);  // publish then increment
    chatter_pub_.Publish(msg);
    std::this_thread::sleep_for(period);
  }
}

}  // namespace class_demo
