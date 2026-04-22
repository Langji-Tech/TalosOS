#ifndef TALOSOS_SERVICE_H_
#define TALOSOS_SERVICE_H_

#include <chrono>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include "talosos/serialization.h"

namespace talos {

class Node;

// ROS1-style non-templated Service server handle. Type parameters only appear
// at Node::AdvertiseService<Req,Resp>() so the handler signature is checked
// at construction time; the handle itself is just an RAII owner.
class Service {
 public:
  using RawHandler = std::function<std::vector<uint8_t>(
      const uint8_t* request, std::size_t length)>;

  Service();
  Service(Service&&) noexcept;
  Service& operator=(Service&&) noexcept;
  Service(const Service&) = delete;
  Service& operator=(const Service&) = delete;
  ~Service();

  const std::string& key() const;
  bool valid() const;

  class Impl;
  explicit Service(std::unique_ptr<Impl> impl);

 private:
  std::unique_ptr<Impl> impl_;
};

// ROS1-style non-templated ServiceClient handle. Call types are deduced from
// the arguments passed to Call(req, resp, ...) — matching what ROS1's
// `client.call(srv)` does where `srv` carries .request and .response members.
class ServiceClient {
 public:
  ServiceClient();
  ServiceClient(ServiceClient&&) noexcept;
  ServiceClient& operator=(ServiceClient&&) noexcept;
  ServiceClient(const ServiceClient&) = delete;
  ServiceClient& operator=(const ServiceClient&) = delete;
  ~ServiceClient();

  const std::string& key() const;
  bool valid() const;

  // Blocking call. Returns true iff the server responded before `timeout`. On
  // success, fills `response`. On timeout or transport error, leaves
  // `response` untouched.
  template <typename Request, typename Response>
  bool Call(const Request& request, Response& response,
            std::chrono::milliseconds timeout = std::chrono::seconds(5)) {
    auto bytes = cdr::Serialize(request);
    std::vector<uint8_t> reply;
    if (!CallBytes(bytes.data(), bytes.size(), reply, timeout)) return false;
    response = cdr::Deserialize<Response>(reply.data(), reply.size());
    return true;
  }

  // Raw-bytes path for interop.
  bool CallBytes(const uint8_t* request, std::size_t request_len,
                 std::vector<uint8_t>& response,
                 std::chrono::milliseconds timeout);

  class Impl;
  explicit ServiceClient(std::unique_ptr<Impl> impl);

 private:
  std::unique_ptr<Impl> impl_;
};

}  // namespace talos

#endif  // TALOSOS_SERVICE_H_
