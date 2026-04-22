// Companion client: subscribes to /chatter_class_node/chatter, optionally
// publishes a /reset message after N samples, and calls /get_count to show
// the service round-trip.

#include <chrono>
#include <cstdlib>
#include <thread>

#include "class_demo/chatter_node.h"
#include "talosos/logging.h"
#include "talosos/messages.h"
#include "talosos/node.h"

int main(int argc, char** argv) {
  const int reset_after = (argc > 1) ? std::atoi(argv[1]) : 5;

  talos::Init(argc, argv);
  auto node = talos::Node::Create("chatter_class_client");

  auto sub = node->Subscribe<talos::msgs::Int64>(
      "/chatter_class_node/chatter",
      [](const talos::msgs::Int64& msg) {
        TALOS_INFO("got count = %lld", static_cast<long long>(msg.data));
      });

  auto reset_pub = node->Advertise<talos::msgs::Empty>(
      "/chatter_class_node/reset");

  auto client = node->CreateServiceClient<talos::msgs::Empty,
                                            class_demo::GetCountResponse>(
      "/chatter_class_node/get_count");

  // Wait a bit so discovery settles.
  std::this_thread::sleep_for(std::chrono::milliseconds(400));

  int seen = 0;
  for (int t = 0; t < 40 && talos::Ok(); ++t) {
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    ++seen;
    if (seen == reset_after) {
      TALOS_WARN("publishing /reset");
      reset_pub.Publish(talos::msgs::Empty{});
    }
    if (seen == reset_after + 4) {
      class_demo::GetCountResponse resp;
      if (client.Call(talos::msgs::Empty{}, resp, std::chrono::seconds(2))) {
        TALOS_INFO("service /get_count -> %lld",
                   static_cast<long long>(resp.count));
      } else {
        TALOS_ERROR("/get_count timed out");
      }
      break;
    }
  }
  return 0;
}
