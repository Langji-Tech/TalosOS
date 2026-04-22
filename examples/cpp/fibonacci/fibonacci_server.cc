#include <chrono>
#include <thread>

#include "talos/fibonacci/FibonacciGoal.h"
#include "talos/fibonacci/FibonacciFeedback.h"
#include "talos/fibonacci/FibonacciResult.h"

#include "talosos/action.h"
#include "talosos/logging.h"
#include "talosos/node.h"

using talos::fibonacci::FibonacciGoal;
using talos::fibonacci::FibonacciFeedback;
using talos::fibonacci::FibonacciResult;

int main(int argc, char** argv) {
  talos::Init(argc, argv);
  auto node = talos::Node::Create("fibonacci_server");

  using Server = talos::ActionServer<FibonacciGoal, FibonacciFeedback,
                                       FibonacciResult>;

  auto execute = [](Server::Handle& h)
      -> std::pair<talos::GoalStatus, FibonacciResult> {
    const int32_t order = h.goal().order;
    TALOS_INFO_NAMED("fib", "goal %s order=%d", h.id().ToString().c_str(), order);
    if (order < 1) {
      return {talos::GoalStatus::kRejected, FibonacciResult{}};
    }
    std::vector<int32_t> seq = {0, 1};

    for (int32_t i = 2; i <= order; ++i) {
      if (h.canceling()) {
        TALOS_WARN_NAMED("fib", "goal canceled at step %d", i);
        FibonacciResult partial;
        partial.sequence = seq;
        return {talos::GoalStatus::kCanceled, partial};
      }
      seq.push_back(seq[i - 1] + seq[i - 2]);

      FibonacciFeedback fb;
      fb.partial_sequence = seq;
      h.PublishFeedback(fb);

      std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }

    FibonacciResult result;
    result.sequence = std::move(seq);
    return {talos::GoalStatus::kSucceeded, std::move(result)};
  };

  auto server = talos::MakeActionServer<FibonacciGoal, FibonacciFeedback,
                                          FibonacciResult>(
      node, "/fibonacci", execute);

  TALOS_INFO("fibonacci action server ready at %s", server.name().c_str());
  node->Spin();
  return 0;
}
