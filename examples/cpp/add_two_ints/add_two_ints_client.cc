// Service client: uses the same generated messages to round-trip through the
// service. Also demonstrates the inline TALOS_MESSAGE_FIELDS path for a
// compile-time identical request shape, to prove both representations are
// CDR-wire-compatible.

#include <chrono>
#include <cstdio>
#include <cstdlib>

#include "talos/add_two_ints/AddTwoIntsRequest.h"
#include "talos/add_two_ints/AddTwoIntsResponse.h"

#include "talosos/logging.h"
#include "talosos/node.h"
#include "talosos/serialization.h"

using talos::add_two_ints::AddTwoIntsRequest;
using talos::add_two_ints::AddTwoIntsResponse;

// Inline variant — identical field layout declared manually.
namespace demo_inline {
struct AddTwoIntsRequest {
  int64_t a = 0;
  int64_t b = 0;
  TALOS_MESSAGE_FIELDS(a, b)
};
}  // namespace demo_inline

int main(int argc, char** argv) {
  const int64_t a = (argc > 1) ? std::atoll(argv[1]) : 7;
  const int64_t b = (argc > 2) ? std::atoll(argv[2]) : 35;

  talos::Init(argc, argv);
  auto node = talos::Node::Create("add_two_ints_client");

  auto client = node->CreateServiceClient<AddTwoIntsRequest, AddTwoIntsResponse>(
      "/add_two_ints");

  AddTwoIntsRequest req;
  req.a = a;
  req.b = b;

  AddTwoIntsResponse resp;
  if (!client.Call(req, resp, std::chrono::seconds(3))) {
    TALOS_ERROR("service call timed out");
    return 1;
  }
  TALOS_INFO("generated path: %ld + %ld -> %ld",
             static_cast<long>(a), static_cast<long>(b),
             static_cast<long>(resp.sum));

  // Verify the inline-declared request matches wire bytes.
  demo_inline::AddTwoIntsRequest inline_req{a, b};
  auto wire_a = talos::cdr::Serialize(req);
  auto wire_b = talos::cdr::Serialize(inline_req);
  if (wire_a != wire_b) {
    TALOS_ERROR("inline vs generated wire bytes differ");
    return 2;
  }
  TALOS_INFO("wire layouts identical between generated and inline request (%zu bytes)",
             wire_a.size());
  return 0;
}
