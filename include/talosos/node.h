#ifndef TALOSOS_NODE_H_
#define TALOSOS_NODE_H_

#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include "talosos/serialization.h"
#include "talosos/service.h"

namespace talos {

// Global lifecycle. Init() installs SIGINT/SIGTERM handlers so Ok() flips to
// false when the user presses Ctrl+C; Shutdown() triggers the same flag
// programmatically. Safe to call Init() multiple times.
void Init(int argc, char** argv);
void Shutdown();
bool Ok();

struct NodeOptions {
  // Namespace prefix. Leading slash optional; empty means none.
  std::string ns = "";

  // Zenoh transport knobs. Leave blank to use zenoh defaults.
  std::string mode = "";                 // "peer" | "client" | "router"
  std::vector<std::string> connect;      // e.g. {"tcp/192.168.1.10:7447"}
  std::vector<std::string> listen;       // e.g. {"tcp/0.0.0.0:7447"}
  bool multicast = true;                 // disable scouting/multicast when false
  std::string config_file;               // zenoh json5 file; overrides other knobs

  // TALOS_DOMAIN environment override is applied via Init(). Explicit value here
  // takes precedence when non-empty.
  std::string domain = "";

  int callback_threads = 1;              // reserved; zenoh manages its own pool
};

class Node;

// ROS1-style non-templated Publisher handle. Template parameter only appears
// at Node::Advertise<T>() and at the individual Publish(msg) call site, where
// T is deduced from the argument.
class Publisher {
 public:
  Publisher();
  Publisher(Publisher&&) noexcept;
  Publisher& operator=(Publisher&&) noexcept;
  Publisher(const Publisher&) = delete;
  Publisher& operator=(const Publisher&) = delete;
  ~Publisher();

  // Publish any T that has a CDR Write overload (primitives, msgs::*, structs
  // using TALOS_MESSAGE_FIELDS, or .msg-generated types).
  template <typename T>
  void Publish(const T& msg) {
    auto buf = cdr::Serialize(msg);
    PublishBytes(buf.data(), buf.size());
  }

  // Raw-bytes escape hatch for interop with pre-encoded payloads.
  void PublishBytes(const uint8_t* data, size_t size);

  const std::string& key() const;
  bool valid() const;

  class Impl;
  explicit Publisher(std::unique_ptr<Impl> impl);

 private:
  std::unique_ptr<Impl> impl_;
};

// ROS1-style non-templated Subscription handle. Ownership keeps the zenoh
// subscriber alive; dropping the Subscription un-declares it.
class Subscription {
 public:
  Subscription();
  Subscription(Subscription&&) noexcept;
  Subscription& operator=(Subscription&&) noexcept;
  Subscription(const Subscription&) = delete;
  Subscription& operator=(const Subscription&) = delete;
  ~Subscription();

  const std::string& key() const;
  bool valid() const;

  class Impl;
  explicit Subscription(std::unique_ptr<Impl> impl);

 private:
  std::unique_ptr<Impl> impl_;
};

using RawSubscriptionCallback =
    std::function<void(const uint8_t* data, size_t size)>;

// ---- Node ----

class Node {
 public:
  // Construct and attach a zenoh session. Use ROS-style topic names:
  //   "/foo"  -> absolute key "foo"
  //   "foo"   -> "<ns>/<name>/foo"
  //   "~/foo" -> "<ns>/<name>/foo"  (explicit private)
  static std::shared_ptr<Node> Create(const std::string& name,
                                       NodeOptions options = {});

  ~Node();

  Node(const Node&) = delete;
  Node& operator=(const Node&) = delete;

  const std::string& name() const;
  const std::string& ns() const;
  std::string FullyQualifiedName() const;

  std::string ResolveTopic(const std::string& topic) const;

  template <typename T>
  Publisher Advertise(const std::string& topic);

  /// Override the broadcast type name (shown in `talos topic info` + rqt).
  template <typename T>
  Publisher Advertise(const std::string& topic, const std::string& type_name);

  // Subscribe — three equivalent call styles:
  //
  //   (1) lambda / std::function (T explicit):
  //         node->Subscribe<Msg>("topic", [this](const Msg& m) { ... });
  //
  //   (2) member-function pointer (ROS1 style — T deduced from the method):
  //         node->Subscribe("topic", &MyClass::OnMsg, this);
  //
  //   (3) std::bind or free function wrapped in std::function works via (1).
  template <typename T>
  Subscription Subscribe(const std::string& topic,
                          std::function<void(const T&)> cb);

  template <typename T, typename Self>
  Subscription Subscribe(const std::string& topic,
                          void (Self::*method)(const T&),
                          Self* instance);

  template <typename T, typename Self>
  Subscription Subscribe(const std::string& topic,
                          void (Self::*method)(const T&) const,
                          const Self* instance);

  // AdvertiseService — same three styles:
  //
  //   (1) lambda / std::function:
  //         node->AdvertiseService<Req,Resp>("name", handler);
  //
  //   (2) member-function pointer:
  //         node->AdvertiseService<Req,Resp>("name", &MyClass::OnCall, this);
  template <typename Request, typename Response>
  Service AdvertiseService(
      const std::string& name,
      std::function<Response(const Request&)> handler);

  template <typename Request, typename Response, typename Self>
  Service AdvertiseService(
      const std::string& name,
      Response (Self::*method)(const Request&),
      Self* instance);

  template <typename Request, typename Response, typename Self>
  Service AdvertiseService(
      const std::string& name,
      Response (Self::*method)(const Request&) const,
      const Self* instance);

  template <typename Request, typename Response>
  ServiceClient CreateServiceClient(const std::string& name);

  // Blocking loop until Ok() becomes false. Callbacks fire on zenoh threads.
  void Spin();

  // Non-blocking tick. Yields the CPU once.
  void SpinOnce();

  // Internal factories used by the templated helpers (public so the inline
  // templates below can find them).
  Publisher CreateRawPublisher(const std::string& topic,
                                const std::string& type_name = "");
  Subscription CreateRawSubscription(const std::string& topic,
                                       RawSubscriptionCallback cb);
  Service CreateRawService(const std::string& name,
                            Service::RawHandler handler);
  ServiceClient CreateRawServiceClient(const std::string& name);

 private:
  Node();
  class Impl;
  std::unique_ptr<Impl> impl_;
};

// ---- Type-name helper ----

// Short, unqualified type name — used by Advertise<T> to broadcast the
// message type via liveliness. On GCC / Clang it demangles typeid(T).name()
// and takes the part after the last `::`. On MSVC the name is already
// readable; we apply the same trimming.
namespace detail {
std::string short_type_name(const char* mangled);
}

template <typename T>
std::string ShortTypeName() {
  return detail::short_type_name(typeid(T).name());
}

// ---- Inline template implementations ----

template <typename T>
Publisher Node::Advertise(const std::string& topic) {
  return CreateRawPublisher(topic, ShortTypeName<T>());
}

template <typename T>
Publisher Node::Advertise(const std::string& topic,
                           const std::string& type_name) {
  return CreateRawPublisher(topic, type_name);
}

template <typename T>
Subscription Node::Subscribe(const std::string& topic,
                              std::function<void(const T&)> cb) {
  auto wrap = [cb = std::move(cb)](const uint8_t* data, size_t size) {
    T msg = cdr::Deserialize<T>(data, size);
    cb(msg);
  };
  return CreateRawSubscription(topic, std::move(wrap));
}

template <typename T, typename Self>
Subscription Node::Subscribe(const std::string& topic,
                              void (Self::*method)(const T&),
                              Self* instance) {
  return Subscribe<T>(topic,
      std::function<void(const T&)>(
          [instance, method](const T& msg) { (instance->*method)(msg); }));
}

template <typename T, typename Self>
Subscription Node::Subscribe(const std::string& topic,
                              void (Self::*method)(const T&) const,
                              const Self* instance) {
  return Subscribe<T>(topic,
      std::function<void(const T&)>(
          [instance, method](const T& msg) { (instance->*method)(msg); }));
}

template <typename Request, typename Response>
Service Node::AdvertiseService(
    const std::string& name,
    std::function<Response(const Request&)> handler) {
  auto wrap = [h = std::move(handler)](const uint8_t* data,
                                         std::size_t len) -> std::vector<uint8_t> {
    Request req = cdr::Deserialize<Request>(data, len);
    Response resp = h(req);
    return cdr::Serialize(resp);
  };
  return CreateRawService(name, std::move(wrap));
}

template <typename Request, typename Response, typename Self>
Service Node::AdvertiseService(
    const std::string& name,
    Response (Self::*method)(const Request&),
    Self* instance) {
  return AdvertiseService<Request, Response>(name,
      std::function<Response(const Request&)>(
          [instance, method](const Request& req) {
            return (instance->*method)(req);
          }));
}

template <typename Request, typename Response, typename Self>
Service Node::AdvertiseService(
    const std::string& name,
    Response (Self::*method)(const Request&) const,
    const Self* instance) {
  return AdvertiseService<Request, Response>(name,
      std::function<Response(const Request&)>(
          [instance, method](const Request& req) {
            return (instance->*method)(req);
          }));
}

template <typename Request, typename Response>
ServiceClient Node::CreateServiceClient(const std::string& name) {
  return CreateRawServiceClient(name);
}

}  // namespace talos

#endif  // TALOSOS_NODE_H_
