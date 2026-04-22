#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
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

static std::string Join(const std::vector<int32_t>& v) {
  std::string s;
  for (size_t i = 0; i < v.size(); ++i) {
    if (i) s += ',';
    s += std::to_string(v[i]);
  }
  return s;
}

int main(int argc, char** argv) {
  int32_t order = (argc > 1) ? std::atoi(argv[1]) : 8;
  bool cancel_mid = (argc > 2 && std::strcmp(argv[2], "--cancel") == 0);

  talos::Init(argc, argv);
  auto node = talos::Node::Create("fibonacci_client");

  auto client = talos::MakeActionClient<FibonacciGoal, FibonacciFeedback,
                                          FibonacciResult>(
      node, "/fibonacci");

  // Give the pub/sub discovery a beat to settle.
  std::this_thread::sleep_for(std::chrono::milliseconds(400));

  FibonacciGoal goal;
  goal.order = order;

  auto handle = client.SendGoal(
      goal, [](const FibonacciFeedback& fb) {
        TALOS_INFO_NAMED("fib", "feedback seq=[%s]",
                          Join(fb.partial_sequence).c_str());
      });

  if (cancel_mid) {
    std::this_thread::sleep_for(std::chrono::milliseconds(600));
    TALOS_WARN_NAMED("fib", "requesting cancel");
    handle->Cancel();
  }

  FibonacciResult result;
  talos::GoalStatus status;
  if (!handle->WaitForResult(std::chrono::seconds(15), result, status)) {
    TALOS_ERROR("action timed out");
    return 1;
  }
  TALOS_INFO("final status=%s sequence=[%s]",
             talos::ToString(status), Join(result.sequence).c_str());
  return status == talos::GoalStatus::kSucceeded ||
         status == talos::GoalStatus::kCanceled
      ? 0
      : 1;
}
