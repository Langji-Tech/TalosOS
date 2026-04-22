// Service server: uses messages generated from .msg files via the codegen path.

#include "talos/add_two_ints/AddTwoIntsRequest.h"
#include "talos/add_two_ints/AddTwoIntsResponse.h"

#include "talosos/logging.h"
#include "talosos/node.h"

using talos::add_two_ints::AddTwoIntsRequest;
using talos::add_two_ints::AddTwoIntsResponse;

int main(int argc, char** argv) {
  talos::Init(argc, argv);
  auto node = talos::Node::Create("add_two_ints_server");

  auto service = node->AdvertiseService<AddTwoIntsRequest, AddTwoIntsResponse>(
      "/add_two_ints",
      [](const AddTwoIntsRequest& req) {
        AddTwoIntsResponse resp;
        resp.sum = req.a + req.b;
        TALOS_INFO("service request %ld + %ld = %ld",
                   static_cast<long>(req.a), static_cast<long>(req.b),
                   static_cast<long>(resp.sum));
        return resp;
      });

  TALOS_INFO("service '%s' ready", service.key().c_str());
  node->Spin();
  return 0;
}
