#include "talosos/logging.h"
#include "talosos/messages.h"
#include "talosos/node.h"

int main(int argc, char** argv) {
  talos::Init(argc, argv);

  auto node = talos::Node::Create("listener");

  auto sub = node->Subscribe<talos::msgs::String>(
      "/talker/chatter",
      [](const talos::msgs::String& msg) {
        TALOS_INFO("received: %s", msg.data.c_str());
      });

  TALOS_INFO("listener bound to %s", sub.key().c_str());
  node->Spin();
  return 0;
}
