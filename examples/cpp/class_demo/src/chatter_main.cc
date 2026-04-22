// Entry point for the class-form example. Creates the Node, wires a
// ChatterNode around it, and blocks on Node::Spin() until SIGINT.

#include <memory>

#include "class_demo/chatter_node.h"
#include "talosos/logging.h"
#include "talosos/node.h"

int main(int argc, char** argv) {
  const double hz = (argc > 1) ? std::atof(argv[1]) : 2.0;

  talos::Init(argc, argv);
  auto node = talos::Node::Create("chatter_class_node");
  class_demo::ChatterNode chatter(node, hz);
  chatter.Start();

  TALOS_INFO("class_demo running at %.1f Hz — Ctrl+C to exit", hz);
  node->Spin();   // blocks until SIGINT; Stop() is called by ~ChatterNode
  return 0;
}
