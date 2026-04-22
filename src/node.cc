#include "talosos/node.h"

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <csignal>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#if defined(__GNUC__) || defined(__clang__)
#  include <cxxabi.h>
#endif

#include <zenoh.hxx>

#include "talosos/logging.h"
#include "talosos/messages.h"
#include "talosos/service.h"

namespace talos {

namespace detail {

std::string short_type_name(const char* mangled) {
  std::string full = mangled ? mangled : "";
#if defined(__GNUC__) || defined(__clang__)
  int status = 0;
  char* demangled = abi::__cxa_demangle(mangled, nullptr, nullptr, &status);
  if (status == 0 && demangled) {
    full = demangled;
  }
  std::free(demangled);
#endif
  // Drop any '<...>' template instantiation tail so we get "Publisher"
  // rather than "Publisher<std::string>".
  auto lt = full.find('<');
  if (lt != std::string::npos) full = full.substr(0, lt);
  // Take the last `::` segment.
  auto pos = full.rfind("::");
  if (pos != std::string::npos) full = full.substr(pos + 2);
  // Strip common prefixes like "class " on MSVC.
  const char* strip[] = {"class ", "struct "};
  for (const char* p : strip) {
    auto plen = std::strlen(p);
    if (full.compare(0, plen, p) == 0) full = full.substr(plen);
  }
  return full;
}

}  // namespace detail

namespace {

std::atomic<bool> g_ok{true};
std::once_flag g_signal_once;

void HandleSignal(int /*signo*/) {
  g_ok.store(false);
}

std::string StripLeadingSlash(const std::string& s) {
  size_t i = 0;
  while (i < s.size() && s[i] == '/') ++i;
  return s.substr(i);
}

std::string JoinKey(const std::string& a, const std::string& b) {
  if (a.empty()) return b;
  if (b.empty()) return a;
  const bool a_trails = (a.back() == '/');
  const bool b_leads = (b.front() == '/');
  if (a_trails && b_leads) return a + b.substr(1);
  if (a_trails || b_leads) return a + b;
  return a + "/" + b;
}

std::string JsonStringArray(const std::vector<std::string>& items) {
  std::string out = "[";
  bool first = true;
  for (const auto& s : items) {
    if (!first) out += ",";
    out += "\"" + s + "\"";
    first = false;
  }
  out += "]";
  return out;
}

}  // namespace

void Init(int /*argc*/, char** /*argv*/) {
  std::call_once(g_signal_once, []() {
    std::signal(SIGINT, HandleSignal);
    std::signal(SIGTERM, HandleSignal);
  });
  g_ok.store(true);
}

void Shutdown() { g_ok.store(false); }
bool Ok() { return g_ok.load(); }

// ---- Time ----

Time Time::Now() {
  const auto now = std::chrono::system_clock::now().time_since_epoch();
  const auto s = std::chrono::duration_cast<std::chrono::seconds>(now);
  const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(now - s);
  Time t;
  t.sec = static_cast<int32_t>(s.count());
  t.nanosec = static_cast<uint32_t>(ns.count());
  return t;
}

double Time::seconds() const {
  return static_cast<double>(sec) + static_cast<double>(nanosec) * 1e-9;
}

// ---- Node::Impl ----

class Node::Impl {
 public:
  std::string name;
  std::string ns;
  NodeOptions options;
  std::unique_ptr<zenoh::Session> session;

  zenoh::Session& zsession() { return *session; }
};

Node::Node() : impl_(std::make_unique<Impl>()) {}
Node::~Node() = default;

const std::string& Node::name() const { return impl_->name; }
const std::string& Node::ns() const { return impl_->ns; }

std::string Node::FullyQualifiedName() const {
  const std::string ns = StripLeadingSlash(impl_->ns);
  return JoinKey(ns, impl_->name);
}

std::string Node::ResolveTopic(const std::string& topic) const {
  if (topic.empty()) return FullyQualifiedName();
  if (topic[0] == '/') {
    return StripLeadingSlash(topic);
  }
  if (topic.size() >= 2 && topic[0] == '~' && topic[1] == '/') {
    return JoinKey(FullyQualifiedName(), topic.substr(2));
  }
  return JoinKey(FullyQualifiedName(), topic);
}

std::shared_ptr<Node> Node::Create(const std::string& name, NodeOptions options) {
  auto node = std::shared_ptr<Node>(new Node());
  node->impl_->name = name;
  node->impl_->ns = options.ns;
  node->impl_->options = std::move(options);

  zenoh::Config cfg = [&]() {
    if (!node->impl_->options.config_file.empty()) {
      return zenoh::Config::from_file(node->impl_->options.config_file);
    }
    return zenoh::Config::create_default();
  }();

  if (node->impl_->options.config_file.empty()) {
    const auto& o = node->impl_->options;
    if (!o.mode.empty()) {
      cfg.insert_json5("mode", "\"" + o.mode + "\"");
    }
    if (!o.connect.empty()) {
      cfg.insert_json5("connect/endpoints", JsonStringArray(o.connect));
    }
    if (!o.listen.empty()) {
      cfg.insert_json5("listen/endpoints", JsonStringArray(o.listen));
    }
    if (!o.multicast) {
      cfg.insert_json5("scouting/multicast/enabled", "false");
    }
  }

  node->impl_->session = std::make_unique<zenoh::Session>(
      zenoh::Session::open(std::move(cfg)));

  TALOS_INFO("node '%s' online (ns='%s', fqn='%s')",
             node->impl_->name.c_str(),
             node->impl_->ns.c_str(),
             node->FullyQualifiedName().c_str());
  return node;
}

void Node::Spin() {
  using namespace std::chrono_literals;
  while (Ok()) {
    std::this_thread::sleep_for(50ms);
  }
}

void Node::SpinOnce() {
  std::this_thread::yield();
}

// ---- Publisher ----

class Publisher::Impl {
 public:
  std::string key;
  std::optional<zenoh::Publisher> publisher;
  std::optional<zenoh::LivelinessToken> live_token;
};

Publisher::Publisher() = default;
Publisher::Publisher(std::unique_ptr<Impl> impl) : impl_(std::move(impl)) {}
Publisher::Publisher(Publisher&&) noexcept = default;
Publisher& Publisher::operator=(Publisher&&) noexcept = default;
Publisher::~Publisher() = default;

const std::string& Publisher::key() const {
  static const std::string kEmpty;
  return impl_ ? impl_->key : kEmpty;
}

bool Publisher::valid() const { return impl_ != nullptr; }

void Publisher::PublishBytes(const uint8_t* data, size_t size) {
  if (!impl_ || !impl_->publisher.has_value()) return;
  std::vector<uint8_t> copy(data, data + size);
  impl_->publisher->put(zenoh::Bytes(std::move(copy)));
}

Publisher Node::CreateRawPublisher(const std::string& topic,
                                     const std::string& type_name) {
  auto pimpl = std::make_unique<Publisher::Impl>();
  pimpl->key = ResolveTopic(topic);
  pimpl->publisher.emplace(
      impl_->session->declare_publisher(zenoh::KeyExpr(pimpl->key)));

  // Discovery: embed the type name in the liveliness key so `talos topic
  // list/info` + rqt can route to the right visualization without heuristics.
  //
  //   with type:  _talos/pub/<key>/_t/<type>/_n/<fqn>
  //   without:    _talos/pub/<key>/_n/<fqn>
  //
  // Parsers on both sides accept either form.
  std::string safe_type = type_name;
  // Type tokens with '/' would break the zenoh key path — strip them.
  for (char& c : safe_type) if (c == '/') c = '_';

  std::string live_key = "_talos/pub/" + pimpl->key;
  if (!safe_type.empty()) live_key += "/_t/" + safe_type;
  live_key += "/_n/" + FullyQualifiedName();

  try {
    pimpl->live_token.emplace(
        impl_->session->liveliness_declare_token(zenoh::KeyExpr(live_key)));
  } catch (const std::exception& ex) {
    TALOS_WARN("liveliness token '%s' failed: %s", live_key.c_str(), ex.what());
  }

  TALOS_DEBUG("advertise '/%s' type=%s", pimpl->key.c_str(),
              type_name.empty() ? "?" : type_name.c_str());
  return Publisher(std::move(pimpl));
}

// ---- Subscription ----

class Subscription::Impl {
 public:
  std::string key;
  std::optional<zenoh::Subscriber<void>> subscriber;
};

Subscription::Subscription() = default;
Subscription::Subscription(std::unique_ptr<Impl> impl)
    : impl_(std::move(impl)) {}
Subscription::Subscription(Subscription&&) noexcept = default;
Subscription& Subscription::operator=(Subscription&&) noexcept = default;
Subscription::~Subscription() = default;

const std::string& Subscription::key() const {
  static const std::string kEmpty;
  return impl_ ? impl_->key : kEmpty;
}

bool Subscription::valid() const { return impl_ != nullptr; }

Subscription Node::CreateRawSubscription(const std::string& topic,
                                               RawSubscriptionCallback cb) {
  auto simpl = std::make_unique<Subscription::Impl>();
  simpl->key = ResolveTopic(topic);

  auto on_sample = [cb = std::move(cb)](const zenoh::Sample& sample) {
    try {
      const auto& payload = sample.get_payload();
      std::vector<uint8_t> buf = payload.as_vector();
      cb(buf.data(), buf.size());
    } catch (const std::exception& ex) {
      TALOS_ERROR("subscription callback threw: %s", ex.what());
    } catch (...) {
      TALOS_ERROR("subscription callback threw unknown exception");
    }
  };
  auto on_drop = []() {};

  simpl->subscriber.emplace(impl_->session->declare_subscriber(
      zenoh::KeyExpr(simpl->key),
      std::move(on_sample),
      std::move(on_drop)));

  TALOS_DEBUG("subscribe '/%s'", simpl->key.c_str());
  return Subscription(std::move(simpl));
}

// ---- Service ----

class Service::Impl {
 public:
  std::string key;
  std::optional<zenoh::Queryable<void>> queryable;
  std::optional<zenoh::LivelinessToken> live_token;
};

Service::Service() = default;
Service::Service(std::unique_ptr<Impl> impl) : impl_(std::move(impl)) {}
Service::Service(Service&&) noexcept = default;
Service& Service::operator=(Service&&) noexcept = default;
Service::~Service() = default;

const std::string& Service::key() const {
  static const std::string kEmpty;
  return impl_ ? impl_->key : kEmpty;
}

bool Service::valid() const { return impl_ != nullptr; }

Service Node::CreateRawService(const std::string& name,
                                     Service::RawHandler handler) {
  auto simpl = std::make_unique<Service::Impl>();
  simpl->key = ResolveTopic(name);

  auto on_query = [h = std::move(handler), key = simpl->key](zenoh::Query& q) {
    try {
      std::vector<uint8_t> request_bytes;
      auto payload_opt = q.get_payload();
      if (payload_opt.has_value()) {
        request_bytes = payload_opt->get().as_vector();
      }
      std::vector<uint8_t> reply_bytes =
          h(request_bytes.data(), request_bytes.size());
      q.reply(zenoh::KeyExpr(key), zenoh::Bytes(std::move(reply_bytes)));
    } catch (const std::exception& ex) {
      TALOS_ERROR("service '%s' handler threw: %s", key.c_str(), ex.what());
      q.reply_err(zenoh::Bytes(std::string(ex.what())));
    } catch (...) {
      TALOS_ERROR("service '%s' handler threw unknown exception", key.c_str());
      q.reply_err(zenoh::Bytes(std::string("unknown exception")));
    }
  };
  auto on_drop = []() {};

  simpl->queryable.emplace(impl_->session->declare_queryable(
      zenoh::KeyExpr(simpl->key),
      std::move(on_query),
      std::move(on_drop)));

  const std::string live_key =
      "_talos/srv/" + simpl->key + "/_n/" + FullyQualifiedName();
  try {
    simpl->live_token.emplace(
        impl_->session->liveliness_declare_token(zenoh::KeyExpr(live_key)));
  } catch (const std::exception& ex) {
    TALOS_WARN("liveliness token '%s' failed: %s", live_key.c_str(), ex.what());
  }

  TALOS_DEBUG("service '/%s' online", simpl->key.c_str());
  return Service(std::move(simpl));
}

// ---- ServiceClient ----

class ServiceClient::Impl {
 public:
  std::string key;
  zenoh::Session* session = nullptr;
};

ServiceClient::ServiceClient() = default;
ServiceClient::ServiceClient(std::unique_ptr<Impl> impl)
    : impl_(std::move(impl)) {}
ServiceClient::ServiceClient(ServiceClient&&) noexcept = default;
ServiceClient& ServiceClient::operator=(ServiceClient&&) noexcept = default;
ServiceClient::~ServiceClient() = default;

const std::string& ServiceClient::key() const {
  static const std::string kEmpty;
  return impl_ ? impl_->key : kEmpty;
}

bool ServiceClient::valid() const {
  return impl_ != nullptr && impl_->session != nullptr;
}

bool ServiceClient::CallBytes(const uint8_t* request, std::size_t request_len,
                                    std::vector<uint8_t>& response,
                                    std::chrono::milliseconds timeout) {
  if (!valid()) return false;

  struct State {
    std::mutex mu;
    std::condition_variable cv;
    bool done = false;
    bool ok = false;
    std::vector<uint8_t> payload;
  };
  auto state = std::make_shared<State>();

  std::vector<uint8_t> req_copy(request, request + request_len);

  zenoh::Session::GetOptions options;
  options.timeout_ms = static_cast<uint64_t>(timeout.count());
  options.payload = zenoh::Bytes(std::move(req_copy));

  auto on_reply = [state](const zenoh::Reply& reply) {
    std::lock_guard<std::mutex> lock(state->mu);
    if (state->done) return;  // only capture the first reply
    if (reply.is_ok()) {
      state->payload = reply.get_ok().get_payload().as_vector();
      state->ok = true;
    }
  };
  auto on_drop = [state]() {
    {
      std::lock_guard<std::mutex> lock(state->mu);
      state->done = true;
    }
    state->cv.notify_all();
  };

  impl_->session->get(zenoh::KeyExpr(impl_->key), "",
                       std::move(on_reply), std::move(on_drop),
                       std::move(options));

  std::unique_lock<std::mutex> lock(state->mu);
  state->cv.wait_for(lock, timeout + std::chrono::milliseconds(100),
                      [&]() { return state->done; });
  if (!state->ok) return false;
  response = std::move(state->payload);
  return true;
}

ServiceClient Node::CreateRawServiceClient(const std::string& name) {
  auto cimpl = std::make_unique<ServiceClient::Impl>();
  cimpl->key = ResolveTopic(name);
  cimpl->session = impl_->session.get();
  TALOS_DEBUG("service client '%s'", cimpl->key.c_str());
  return ServiceClient(std::move(cimpl));
}

}  // namespace talos