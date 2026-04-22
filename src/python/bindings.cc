// pybind11 bindings for the TalosOS C++ runtime. Exposes Node, Publisher,
// Subscription, and the service client/server at the byte level so the
// Python side can layer its existing messages.py codecs on top.

#include <pybind11/functional.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <chrono>
#include <cstring>
#include <memory>
#include <mutex>
#include <queue>
#include <string>
#include <vector>

#include "talosos/logging.h"
#include "talosos/node.h"
#include "talosos/service.h"

namespace py = pybind11;

namespace {

// ----- Publisher (raw bytes) -----

class PyPublisher {
 public:
  explicit PyPublisher(talos::Publisher base)
      : base_(std::make_shared<talos::Publisher>(std::move(base))) {}

  void Publish(py::bytes payload) {
    std::string s = payload;  // cheap on CPython (view into the object)
    base_->PublishBytes(reinterpret_cast<const uint8_t*>(s.data()), s.size());
  }

  std::string key() const { return base_->key(); }
  bool valid() const { return base_->valid(); }

 private:
  std::shared_ptr<talos::Publisher> base_;
};

// ----- Subscription (raw bytes; callback released to Python via GIL) -----

class PySubscription {
 public:
  explicit PySubscription(talos::Subscription base)
      : base_(std::make_shared<talos::Subscription>(std::move(base))) {}

  std::string key() const { return base_->key(); }
  bool valid() const { return base_->valid(); }

 private:
  std::shared_ptr<talos::Subscription> base_;
};

// ----- Service server (raw bytes) -----

class PyService {
 public:
  explicit PyService(talos::Service base)
      : base_(std::make_shared<talos::Service>(std::move(base))) {}

  std::string key() const { return base_->key(); }
  bool valid() const { return base_->valid(); }

 private:
  std::shared_ptr<talos::Service> base_;
};

// ----- Service client -----

class PyServiceClient {
 public:
  explicit PyServiceClient(talos::ServiceClient base)
      : base_(std::make_shared<talos::ServiceClient>(std::move(base))) {}

  py::object Call(py::bytes request, int timeout_ms) {
    std::string s = request;
    std::vector<uint8_t> resp;
    bool ok = false;
    {
      py::gil_scoped_release release;
      ok = base_->CallBytes(reinterpret_cast<const uint8_t*>(s.data()),
                              s.size(), resp,
                              std::chrono::milliseconds(timeout_ms));
    }
    if (!ok) return py::none();
    return py::bytes(reinterpret_cast<const char*>(resp.data()), resp.size());
  }

  std::string key() const { return base_->key(); }
  bool valid() const { return base_->valid(); }

 private:
  std::shared_ptr<talos::ServiceClient> base_;
};

// ----- Node -----

class PyNode {
 public:
  static std::shared_ptr<PyNode> Create(const std::string& name,
                                         const talos::NodeOptions& options) {
    return std::shared_ptr<PyNode>(new PyNode(name, options));
  }

  const std::string& name() const { return node_->name(); }
  const std::string& ns() const { return node_->ns(); }
  std::string fully_qualified_name() const { return node_->FullyQualifiedName(); }
  std::string resolve_topic(const std::string& topic) const {
    return node_->ResolveTopic(topic);
  }

  PyPublisher Advertise(const std::string& topic) {
    return PyPublisher(node_->CreateRawPublisher(topic));
  }

  PySubscription Subscribe(const std::string& topic, py::function cb) {
    auto wrapped = [cb](const uint8_t* data, size_t len) {
      py::gil_scoped_acquire gil;
      try {
        cb(py::bytes(reinterpret_cast<const char*>(data), len));
      } catch (const py::error_already_set& e) {
        TALOS_ERROR("python subscription callback raised: %s", e.what());
      }
    };
    return PySubscription(node_->CreateRawSubscription(topic, std::move(wrapped)));
  }

  PyService AdvertiseService(const std::string& name, py::function handler) {
    auto wrapped = [handler](const uint8_t* data,
                              std::size_t len) -> std::vector<uint8_t> {
      py::gil_scoped_acquire gil;
      py::bytes req(reinterpret_cast<const char*>(data), len);
      try {
        py::object out = handler(req);
        if (out.is_none()) return {};
        std::string s = py::bytes(out);
        return std::vector<uint8_t>(s.begin(), s.end());
      } catch (const py::error_already_set& e) {
        TALOS_ERROR("python service handler raised: %s", e.what());
        return {};
      }
    };
    return PyService(node_->CreateRawService(name, std::move(wrapped)));
  }

  PyServiceClient CreateServiceClient(const std::string& name) {
    return PyServiceClient(node_->CreateRawServiceClient(name));
  }

  void Spin() {
    py::gil_scoped_release release;
    node_->Spin();
  }

 private:
  PyNode(const std::string& name, const talos::NodeOptions& options)
      : node_(talos::Node::Create(name, options)) {}

  std::shared_ptr<talos::Node> node_;
};

}  // namespace

PYBIND11_MODULE(_talosos_runtime, m) {
  m.doc() = "TalosOS C++ runtime bindings (pybind11).";

  m.def("init", [](std::vector<std::string> argv) {
    std::vector<char*> raw;
    for (auto& s : argv) raw.push_back(s.data());
    talos::Init(static_cast<int>(raw.size()), raw.data());
  }, py::arg("argv") = std::vector<std::string>{},
     "Install signal handlers; call once per process.");

  m.def("ok", &talos::Ok, "Returns false after SIGINT/SIGTERM.");
  m.def("shutdown", &talos::Shutdown);

  py::class_<talos::NodeOptions>(m, "NodeOptions")
      .def(py::init<>())
      .def_readwrite("ns", &talos::NodeOptions::ns)
      .def_readwrite("mode", &talos::NodeOptions::mode)
      .def_readwrite("connect", &talos::NodeOptions::connect)
      .def_readwrite("listen", &talos::NodeOptions::listen)
      .def_readwrite("multicast", &talos::NodeOptions::multicast)
      .def_readwrite("config_file", &talos::NodeOptions::config_file)
      .def_readwrite("domain", &talos::NodeOptions::domain)
      .def_readwrite("callback_threads", &talos::NodeOptions::callback_threads);

  py::class_<PyPublisher>(m, "Publisher")
      .def("publish", &PyPublisher::Publish, py::arg("payload"))
      .def_property_readonly("key", &PyPublisher::key)
      .def_property_readonly("valid", &PyPublisher::valid);

  py::class_<PySubscription>(m, "Subscription")
      .def_property_readonly("key", &PySubscription::key)
      .def_property_readonly("valid", &PySubscription::valid);

  py::class_<PyService>(m, "Service")
      .def_property_readonly("key", &PyService::key)
      .def_property_readonly("valid", &PyService::valid);

  py::class_<PyServiceClient>(m, "ServiceClient")
      .def("call", &PyServiceClient::Call,
           py::arg("request"), py::arg("timeout_ms") = 3000,
           "Returns response bytes on success, None on timeout.")
      .def_property_readonly("key", &PyServiceClient::key)
      .def_property_readonly("valid", &PyServiceClient::valid);

  py::class_<PyNode, std::shared_ptr<PyNode>>(m, "Node")
      .def_static("create", &PyNode::Create,
                  py::arg("name"),
                  py::arg("options") = talos::NodeOptions{})
      .def_property_readonly("name", &PyNode::name)
      .def_property_readonly("ns", &PyNode::ns)
      .def_property_readonly("fully_qualified_name",
                              &PyNode::fully_qualified_name)
      .def("resolve_topic", &PyNode::resolve_topic, py::arg("topic"))
      .def("advertise", &PyNode::Advertise, py::arg("topic"))
      .def("subscribe", &PyNode::Subscribe,
           py::arg("topic"), py::arg("callback"))
      .def("advertise_service", &PyNode::AdvertiseService,
           py::arg("name"), py::arg("handler"))
      .def("create_service_client", &PyNode::CreateServiceClient,
           py::arg("name"))
      .def("spin", &PyNode::Spin,
           "Block until Ctrl+C. Releases the GIL while waiting.");
}
