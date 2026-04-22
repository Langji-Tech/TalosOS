// talosos_tool: the C++ helper invoked by `talos topic …` / `talos service …`.
// Subcommands are intentionally thin — each one does a specific zenoh
// operation and prints results in a format the Python CLI can consume or
// forward verbatim.

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <map>
#include <mutex>
#include <optional>
#include <set>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include <zenoh.hxx>

namespace {

struct CliOptions {
  std::string command;             // "topic-echo", "topic-pub", ...
  std::string key;                 // topic / service key (post-prefix resolve)
  std::string data_hex;            // for topic-pub, service-call (hex)
  std::string data_utf8;           // for topic-pub
  uint64_t count = 0;              // 0 = unbounded (echo/hz/bw)
  double rate = 1.0;               // for topic-pub
  double window = 1.0;             // hz/bw averaging window (seconds)
  double report_period = 1.0;      // hz/bw report cadence (seconds)
  uint64_t timeout_ms = 1000;      // topic-list, service-call
  std::string mode;                // peer|client|router
  std::vector<std::string> connect;
  std::vector<std::string> listen;
  bool multicast = true;
  std::string node_name = "talosos_tool";
  std::string node_ns;
  bool no_truncate = false;        // topic-echo: emit full hex (used by plot/viz)
};

[[noreturn]] void Die(const std::string& msg) {
  std::fprintf(stderr, "talosos_tool: %s\n", msg.c_str());
  std::exit(2);
}

std::vector<uint8_t> HexDecode(const std::string& hex) {
  std::vector<uint8_t> out;
  out.reserve(hex.size() / 2);
  auto nybble = [](char c) -> int {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
  };
  for (size_t i = 0; i + 1 < hex.size(); i += 2) {
    int hi = nybble(hex[i]);
    int lo = nybble(hex[i + 1]);
    if (hi < 0 || lo < 0) Die("invalid hex in --hex payload");
    out.push_back(static_cast<uint8_t>((hi << 4) | lo));
  }
  return out;
}

std::string HexEncode(const uint8_t* data, size_t len, size_t max = 64) {
  static const char* kHex = "0123456789abcdef";
  std::string out;
  const size_t n = std::min(len, max);
  out.reserve(n * 2 + 4);
  for (size_t i = 0; i < n; ++i) {
    out.push_back(kHex[data[i] >> 4]);
    out.push_back(kHex[data[i] & 0xF]);
  }
  if (len > max) out += "...";
  return out;
}

std::string JsonStringArray(const std::vector<std::string>& xs) {
  std::string s = "[";
  for (size_t i = 0; i < xs.size(); ++i) {
    if (i) s += ",";
    s += "\"" + xs[i] + "\"";
  }
  return s + "]";
}

// Split a zenoh key expression by '/', preserving empty segments-less parsing
// (we don't expect empty segments in canonical keys).
std::vector<std::string> SplitSlash(const std::string& s) {
  std::vector<std::string> parts;
  std::string cur;
  for (char c : s) {
    if (c == '/') {
      parts.push_back(std::move(cur));
      cur.clear();
    } else {
      cur.push_back(c);
    }
  }
  parts.push_back(std::move(cur));
  return parts;
}

zenoh::Session OpenSession(const CliOptions& o) {
  zenoh::Config cfg = zenoh::Config::create_default();
  if (!o.mode.empty()) cfg.insert_json5("mode", "\"" + o.mode + "\"");
  if (!o.connect.empty()) {
    cfg.insert_json5("connect/endpoints", JsonStringArray(o.connect));
  }
  if (!o.listen.empty()) {
    cfg.insert_json5("listen/endpoints", JsonStringArray(o.listen));
  }
  if (!o.multicast) {
    cfg.insert_json5("scouting/multicast/enabled", "false");
  }
  return zenoh::Session::open(std::move(cfg));
}

// ---- Subcommand implementations ----

int RunTopicEcho(const CliOptions& o, zenoh::Session& session) {
  std::atomic<uint64_t> received{0};
  std::atomic<bool> done{false};
  const uint64_t target = o.count;
  const size_t hex_cap =
      o.no_truncate ? std::numeric_limits<size_t>::max() : size_t{64};

  auto on_sample = [&](const zenoh::Sample& sample) {
    auto bytes = sample.get_payload().as_vector();
    const uint64_t idx = received.fetch_add(1);
    auto kv = sample.get_keyexpr().as_string_view();
    // Display ROS-style topic names with a leading '/'.
    const char* slash = (!kv.empty() && kv.front() == '/') ? "" : "/";
    std::printf("#%llu key=%s%.*s bytes=%zu data_hex=%s\n",
                static_cast<unsigned long long>(idx),
                slash,
                static_cast<int>(kv.size()), kv.data(),
                bytes.size(),
                HexEncode(bytes.data(), bytes.size(), hex_cap).c_str());
    std::fflush(stdout);
    if (target && received.load() >= target) done.store(true);
  };
  auto on_drop = []() {};

  auto sub = session.declare_subscriber(
      zenoh::KeyExpr(o.key), std::move(on_sample), std::move(on_drop));

  using namespace std::chrono_literals;
  while (!done.load()) {
    std::this_thread::sleep_for(50ms);
  }
  return 0;
}

int RunTopicPub(const CliOptions& o, zenoh::Session& session) {
  std::vector<uint8_t> payload;
  if (!o.data_hex.empty()) {
    payload = HexDecode(o.data_hex);
  } else if (!o.data_utf8.empty()) {
    payload.assign(o.data_utf8.begin(), o.data_utf8.end());
  } else {
    Die("topic-pub requires --hex or --utf8 payload");
  }

  auto publisher = session.declare_publisher(zenoh::KeyExpr(o.key));
  const auto period =
      std::chrono::microseconds(static_cast<long long>(1'000'000.0 / o.rate));
  const uint64_t target = o.count ? o.count : 1;

  for (uint64_t i = 0; i < target; ++i) {
    publisher.put(zenoh::Bytes(std::vector<uint8_t>(payload)));
    std::printf("sent #%llu bytes=%zu -> %s\n",
                static_cast<unsigned long long>(i), payload.size(),
                o.key.c_str());
    std::fflush(stdout);
    if (i + 1 < target) std::this_thread::sleep_for(period);
  }
  return 0;
}

int RunTopicHzOrBw(const CliOptions& o, zenoh::Session& session, bool bw) {
  std::mutex mu;
  struct Sample { std::chrono::steady_clock::time_point t; size_t bytes; };
  std::vector<Sample> ring;
  ring.reserve(1024);

  auto on_sample = [&](const zenoh::Sample& sample) {
    auto bytes = sample.get_payload().as_vector();
    std::lock_guard<std::mutex> lock(mu);
    ring.push_back({std::chrono::steady_clock::now(), bytes.size()});
  };
  auto on_drop = []() {};

  auto sub = session.declare_subscriber(
      zenoh::KeyExpr(o.key), std::move(on_sample), std::move(on_drop));

  using clock = std::chrono::steady_clock;
  const auto window = std::chrono::duration<double>(o.window);
  const auto period = std::chrono::duration<double>(o.report_period);

  auto deadline = clock::now();
  uint64_t reports = 0;
  while (true) {
    deadline += std::chrono::duration_cast<clock::duration>(period);
    std::this_thread::sleep_until(deadline);

    std::lock_guard<std::mutex> lock(mu);
    const auto cutoff =
        clock::now() - std::chrono::duration_cast<clock::duration>(window);
    ring.erase(
        std::remove_if(ring.begin(), ring.end(),
                       [&](const Sample& s) { return s.t < cutoff; }),
        ring.end());

    const size_t n = ring.size();
    if (bw) {
      size_t total_bytes = 0;
      for (const auto& s : ring) total_bytes += s.bytes;
      const double b_per_s =
          n >= 2
              ? static_cast<double>(total_bytes) /
                    std::chrono::duration<double>(ring.back().t -
                                                    ring.front().t).count()
              : 0.0;
      std::printf("%8.1f B/s  (%zu samples in %.1fs)\n",
                  b_per_s, n, o.window);
    } else {
      const double hz =
          n >= 2 ? static_cast<double>(n - 1) /
                       std::chrono::duration<double>(ring.back().t -
                                                      ring.front().t).count()
                 : 0.0;
      std::printf("%8.2f Hz   (%zu samples in %.1fs)\n", hz, n, o.window);
    }
    std::fflush(stdout);
    if (o.count && ++reports >= o.count) break;
  }
  return 0;
}

int RunListLiveliness(const CliOptions& o, zenoh::Session& session,
                        const std::string& root) {
  // Output format (tab-separated, one line per unique <key, type>):
  //   <topic_key>\t<type_name_or_empty>\t<node1,node2,...>
  //
  // Publishers that don't broadcast a type produce <type_name_or_empty> = "".
  // liveliness key schema:
  //   _talos/<kind>/<key_parts.../>[_t/<type>/]_n/<node_parts...>
  struct Entry {
    std::string type;
    std::set<std::string> nodes;
  };
  std::mutex mu;
  std::map<std::string, Entry> registry;    // topic_key -> Entry
  std::atomic<bool> done{false};

  auto on_reply = [&](const zenoh::Reply& reply) {
    if (!reply.is_ok()) return;
    const auto& sample = reply.get_ok();
    std::string k{sample.get_keyexpr().as_string_view()};
    auto parts = SplitSlash(k);
    if (parts.size() < 4) return;
    if (parts[0] != "_talos") return;

    // Scan for `_t` and `_n` markers.
    size_t t_at = parts.size();
    size_t n_at = parts.size();
    for (size_t i = 2; i < parts.size(); ++i) {
      if (parts[i] == "_t" && t_at == parts.size()) { t_at = i; }
      else if (parts[i] == "_n" && n_at == parts.size()) { n_at = i; break; }
    }
    if (n_at == parts.size() || n_at + 1 >= parts.size()) return;

    // Topic key: parts[2 .. t_at-1] if type present, else parts[2 .. n_at-1]
    const size_t key_end = (t_at < n_at) ? t_at : n_at;
    std::string key;
    for (size_t i = 2; i < key_end; ++i) {
      if (i > 2) key.push_back('/');
      key += parts[i];
    }
    std::string type;
    if (t_at < n_at && t_at + 1 < n_at) {
      // type could also span multiple segments if escaped, but our safe_type
      // replaces '/' with '_', so expect a single segment.
      for (size_t i = t_at + 1; i < n_at; ++i) {
        if (i > t_at + 1) type.push_back('/');
        type += parts[i];
      }
    }
    std::string node;
    for (size_t i = n_at + 1; i < parts.size(); ++i) {
      if (i > n_at + 1) node.push_back('/');
      node += parts[i];
    }

    std::lock_guard<std::mutex> lock(mu);
    auto& e = registry[key];
    if (!type.empty() && e.type.empty()) e.type = type;
    e.nodes.insert(node);
  };
  auto on_drop = [&]() { done.store(true); };

  zenoh::Session::LivelinessGetOptions opts;
  opts.timeout_ms = o.timeout_ms;
  session.liveliness_get(zenoh::KeyExpr(root + "/**"),
                           std::move(on_reply), std::move(on_drop),
                           std::move(opts));

  using namespace std::chrono;
  const auto deadline = steady_clock::now() + milliseconds(o.timeout_ms + 200);
  while (!done.load() && steady_clock::now() < deadline) {
    std::this_thread::sleep_for(milliseconds(20));
  }

  std::lock_guard<std::mutex> lock(mu);
  for (const auto& [key, e] : registry) {
    std::string joined;
    for (auto it = e.nodes.begin(); it != e.nodes.end(); ++it) {
      if (it != e.nodes.begin()) joined += ",";
      joined += *it;
    }
    std::printf("%s\t%s\t%s\n", key.c_str(), e.type.c_str(), joined.c_str());
  }
  return 0;
}

int RunServiceCall(const CliOptions& o, zenoh::Session& session) {
  std::vector<uint8_t> req;
  if (!o.data_hex.empty()) req = HexDecode(o.data_hex);
  else if (!o.data_utf8.empty()) req.assign(o.data_utf8.begin(), o.data_utf8.end());

  struct State {
    std::mutex mu;
    bool done = false;
    bool ok = false;
    std::vector<uint8_t> payload;
    std::string err;
  };
  auto state = std::make_shared<State>();

  zenoh::Session::GetOptions opts;
  opts.timeout_ms = o.timeout_ms;
  if (!req.empty()) opts.payload = zenoh::Bytes(std::move(req));

  auto on_reply = [state](const zenoh::Reply& reply) {
    std::lock_guard<std::mutex> lock(state->mu);
    if (state->done) return;
    if (reply.is_ok()) {
      state->payload = reply.get_ok().get_payload().as_vector();
      state->ok = true;
    } else {
      auto err_bytes = reply.get_err().get_payload().as_vector();
      state->err.assign(err_bytes.begin(), err_bytes.end());
    }
  };
  auto on_drop = [state]() {
    std::lock_guard<std::mutex> lock(state->mu);
    state->done = true;
  };

  session.get(zenoh::KeyExpr(o.key), "", std::move(on_reply),
               std::move(on_drop), std::move(opts));

  using namespace std::chrono;
  const auto deadline =
      steady_clock::now() + milliseconds(o.timeout_ms + 200);
  while (true) {
    {
      std::lock_guard<std::mutex> lock(state->mu);
      if (state->done) break;
    }
    if (steady_clock::now() >= deadline) break;
    std::this_thread::sleep_for(milliseconds(20));
  }

  std::lock_guard<std::mutex> lock(state->mu);
  if (state->ok) {
    std::printf("bytes=%zu data_hex=%s\n", state->payload.size(),
                HexEncode(state->payload.data(), state->payload.size(),
                            state->payload.size())
                    .c_str());
    return 0;
  }
  if (!state->err.empty()) {
    std::fprintf(stderr, "service error: %s\n", state->err.c_str());
    return 1;
  }
  std::fprintf(stderr, "service call timed out\n");
  return 1;
}

// ---- Argument parsing ----

void Usage() {
  std::fprintf(stderr, R"USAGE(talosos_tool <subcommand> [options]

Subcommands:
  topic-pub   KEY --hex HEX | --utf8 STRING [--count N] [--rate HZ]
  topic-echo  KEY [--count N]
  topic-hz    KEY [--count N] [--window S] [--report-period S]
  topic-bw    KEY [--count N] [--window S] [--report-period S]
  topic-list  [--timeout-ms MS]
  service-call KEY --hex HEX | --utf8 STRING [--timeout-ms MS]
  service-list [--timeout-ms MS]

Common options:
  --mode peer|client|router   --connect ENDPOINT (repeatable)
  --listen ENDPOINT (repeatable)  --no-multicast
  --node-name NAME  --node-ns NS
)USAGE");
}

CliOptions ParseArgs(int argc, char** argv) {
  if (argc < 2) { Usage(); std::exit(2); }
  CliOptions o;
  o.command = argv[1];
  int i = 2;
  // Positional key for most commands
  if (i < argc && argv[i][0] != '-') {
    o.key = argv[i++];
  }
  auto next = [&](const char* flag) -> const char* {
    if (i >= argc) Die(std::string("missing value for ") + flag);
    return argv[i++];
  };
  while (i < argc) {
    std::string f = argv[i++];
    if (f == "--hex") o.data_hex = next("--hex");
    else if (f == "--utf8") o.data_utf8 = next("--utf8");
    else if (f == "--count") o.count = std::strtoull(next("--count"), nullptr, 10);
    else if (f == "--rate") o.rate = std::atof(next("--rate"));
    else if (f == "--window") o.window = std::atof(next("--window"));
    else if (f == "--report-period") o.report_period = std::atof(next("--report-period"));
    else if (f == "--timeout-ms") o.timeout_ms = std::strtoull(next("--timeout-ms"), nullptr, 10);
    else if (f == "--mode") o.mode = next("--mode");
    else if (f == "--connect") o.connect.push_back(next("--connect"));
    else if (f == "--listen") o.listen.push_back(next("--listen"));
    else if (f == "--no-multicast") o.multicast = false;
    else if (f == "--node-name") o.node_name = next("--node-name");
    else if (f == "--node-ns") o.node_ns = next("--node-ns");
    else if (f == "--no-truncate") o.no_truncate = true;
    else if (f == "--help" || f == "-h") { Usage(); std::exit(0); }
    else Die("unknown option: " + f);
  }
  return o;
}

}  // namespace

int main(int argc, char** argv) {
  auto o = ParseArgs(argc, argv);
  auto session = OpenSession(o);

  if (o.command == "topic-pub")      return RunTopicPub(o, session);
  if (o.command == "topic-echo")     return RunTopicEcho(o, session);
  if (o.command == "topic-hz")       return RunTopicHzOrBw(o, session, false);
  if (o.command == "topic-bw")       return RunTopicHzOrBw(o, session, true);
  if (o.command == "topic-list")     return RunListLiveliness(o, session, "_talos/pub");
  if (o.command == "service-list")   return RunListLiveliness(o, session, "_talos/srv");
  if (o.command == "service-call")   return RunServiceCall(o, session);

  Usage();
  return 2;
}
