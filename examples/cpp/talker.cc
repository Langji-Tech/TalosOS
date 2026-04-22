#include <chrono>
#include <string>
#include <thread>

#include "talosos/logging.h"
#include "talosos/messages.h"
#include "talosos/node.h"

int main(int argc, char** argv) {
  talos::Init(argc, argv);

  auto node = talos::Node::Create("talker");
  auto pub = node->Advertise<talos::msgs::String>("chatter");

  int count = 0;
  using namespace std::chrono_literals;
  while (talos::Ok()) {
    talos::msgs::String msg;
    msg.data = "hello from talker #" + std::to_string(count++);

    pub.Publish(msg);
    TALOS_INFO("publish '%s' -> %s", msg.data.c_str(), pub.key().c_str());

    std::this_thread::sleep_for(500ms);
  }

  TALOS_INFO("talker shutting down");
  return 0;
}
