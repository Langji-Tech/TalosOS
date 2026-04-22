// Image transport latency benchmark.
//
// Runs N parallel publishers + N parallel subscribers against TalosOS /
// zenoh and reports per-topic + aggregate end-to-end latency (p50/p90/p99).
// The payload is real PNG bytes (default: the repo's image.png) to approximate
// a real camera workload; swap via --image or use --payload-size for synthetic
// data.
//
// Usage:
//   image_bench --role pub  --topics 10 --hz 10
//   image_bench --role sub  --topics 10 --report 2.0
//   image_bench --role both --topics 10 --hz 10 --duration 20
//
// For a realistic measurement run publisher and subscriber in SEPARATE
// processes (same machine is fine; wall-clock is shared). `--role both`
// keeps them in one process — useful for sanity only.

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <deque>
#include <fstream>
#include <memory>
#include <mutex>
#include <numeric>
#include <string>
#include <thread>
#include <vector>

#include "talosos/logging.h"
#include "talosos/messages.h"
#include "talosos/node.h"

namespace {

using clock = std::chrono::system_clock;

// ---- CLI ----

struct Options {
  std::string role = "both";     // pub | sub | both
  int topics = 10;
  double hz = 10.0;
  double duration_s = 0.0;       // 0 = run forever
  double report_s = 2.0;
  int window = 2000;             // per-topic rolling sample count for percentiles
  std::string image = "/home/ubuntu24/Software/TalosOS/image.png";
  size_t synthetic_bytes = 0;    // overrides --image when > 0
  std::string topic_prefix = "/bench/image_";
};

Options ParseArgs(int argc, char** argv) {
  Options o;
  for (int i = 1; i < argc; ++i) {
    std::string a = argv[i];
    auto need = [&](const char* f) {
      if (i + 1 >= argc) { std::fprintf(stderr, "missing value for %s\n", f); std::exit(2); }
      return std::string(argv[++i]);
    };
    if      (a == "--role")           o.role = need("--role");
    else if (a == "--topics")         o.topics = std::atoi(need("--topics").c_str());
    else if (a == "--hz")             o.hz = std::atof(need("--hz").c_str());
    else if (a == "--duration")       o.duration_s = std::atof(need("--duration").c_str());
    else if (a == "--report")         o.report_s = std::atof(need("--report").c_str());
    else if (a == "--window")         o.window = std::atoi(need("--window").c_str());
    else if (a == "--image")          o.image = need("--image");
    else if (a == "--payload-size")   o.synthetic_bytes = std::strtoull(need("--payload-size").c_str(), nullptr, 10);
    else if (a == "--topic-prefix")   o.topic_prefix = need("--topic-prefix");
    else if (a == "--help" || a == "-h") {
      std::printf("image_bench — zenoh/TalosOS image latency benchmark\n"
                  "  --role pub|sub|both   (default: both)\n"
                  "  --topics N            (default: 10)\n"
                  "  --hz FLOAT            publish rate per topic (default: 10)\n"
                  "  --duration SECONDS    stop after N seconds (0 = forever)\n"
                  "  --report SECONDS      subscriber report cadence (default: 2)\n"
                  "  --window N            rolling sample count per topic (default: 2000)\n"
                  "  --image PATH          payload image file\n"
                  "  --payload-size BYTES  use synthetic bytes instead of --image\n"
                  "  --topic-prefix PFX    topic key prefix (default: /bench/image_)\n");
      std::exit(0);
    }
    else { std::fprintf(stderr, "unknown arg: %s\n", a.c_str()); std::exit(2); }
  }
  return o;
}

std::vector<uint8_t> LoadPayload(const Options& o) {
  if (o.synthetic_bytes > 0) {
    std::vector<uint8_t> buf(o.synthetic_bytes);
    for (size_t i = 0; i < buf.size(); ++i) buf[i] = static_cast<uint8_t>(i & 0xFF);
    return buf;
  }
  std::ifstream f(o.image, std::ios::binary | std::ios::ate);
  if (!f) { std::fprintf(stderr, "cannot open %s\n", o.image.c_str()); std::exit(2); }
  std::vector<uint8_t> buf(f.tellg());
  f.seekg(0);
  f.read(reinterpret_cast<char*>(buf.data()), buf.size());
  return buf;
}

uint64_t NowNs() {
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
             clock::now().time_since_epoch()).count();
}

// ---- Stats ----

struct TopicStats {
  std::string topic;
  std::atomic<uint64_t> received{0};
  std::atomic<uint64_t> bytes{0};
  std::atomic<uint64_t> last_seq{0};
  std::mutex mu;
  std::deque<uint64_t> samples_ns;   // rolling window of latencies
  size_t window_cap = 2000;
};

void PushSample(TopicStats& s, uint64_t lat_ns) {
  std::lock_guard<std::mutex> lock(s.mu);
  s.samples_ns.push_back(lat_ns);
  while (s.samples_ns.size() > s.window_cap) s.samples_ns.pop_front();
}

struct Summary {
  uint64_t count = 0;
  double mean_ms = 0, p50_ms = 0, p90_ms = 0, p99_ms = 0;
  double min_ms = 0, max_ms = 0;
};

Summary SummarizeLocked(const std::deque<uint64_t>& s) {
  Summary out;
  if (s.empty()) return out;
  out.count = s.size();
  std::vector<uint64_t> v(s.begin(), s.end());
  std::sort(v.begin(), v.end());
  auto pct = [&](double q) {
    size_t idx = std::min(v.size() - 1,
                             static_cast<size_t>(q * (v.size() - 1)));
    return v[idx] / 1e6;
  };
  out.min_ms  = v.front() / 1e6;
  out.max_ms  = v.back()  / 1e6;
  out.p50_ms  = pct(0.50);
  out.p90_ms  = pct(0.90);
  out.p99_ms  = pct(0.99);
  out.mean_ms = std::accumulate(v.begin(), v.end(), uint64_t{0}) /
                  static_cast<double>(v.size()) / 1e6;
  return out;
}

using TopicStatsVec = std::vector<std::unique_ptr<TopicStats>>;

void Report(TopicStatsVec& stats, double window_s) {
  uint64_t total_msgs = 0;
  uint64_t total_bytes = 0;
  std::vector<uint64_t> all_samples;

  std::printf("\n== latency report (last %.1fs window, samples capped at %zu/topic) ==\n",
              window_s, stats.empty() ? 0ul : stats[0]->window_cap);
  std::printf("%-20s %8s %12s %8s %8s %8s %8s %8s %8s\n",
              "topic", "msgs", "bytes/s", "min", "p50", "p90", "p99", "max", "mean");

  for (auto& sp : stats) {
    TopicStats& s = *sp;
    Summary sum;
    {
      std::lock_guard<std::mutex> lock(s.mu);
      sum = SummarizeLocked(s.samples_ns);
      all_samples.insert(all_samples.end(),
                           s.samples_ns.begin(), s.samples_ns.end());
    }
    total_msgs += s.received.load();
    total_bytes += s.bytes.load();
    const double bps = s.bytes.load() / std::max(0.001, window_s);
    std::printf("%-20s %8llu %12.1f %8.2f %8.2f %8.2f %8.2f %8.2f %8.2f\n",
                s.topic.c_str(),
                static_cast<unsigned long long>(sum.count),
                bps,
                sum.min_ms, sum.p50_ms, sum.p90_ms, sum.p99_ms,
                sum.max_ms, sum.mean_ms);
    s.received.store(0);
    s.bytes.store(0);
  }

  // Aggregate across topics.
  Summary agg;
  if (!all_samples.empty()) {
    std::deque<uint64_t> d(all_samples.begin(), all_samples.end());
    agg = SummarizeLocked(d);
  }
  std::printf("%-20s %8llu %12.1f %8.2f %8.2f %8.2f %8.2f %8.2f %8.2f   (ms)\n",
              "ALL",
              static_cast<unsigned long long>(agg.count),
              total_bytes / std::max(0.001, window_s),
              agg.min_ms, agg.p50_ms, agg.p90_ms, agg.p99_ms,
              agg.max_ms, agg.mean_ms);
}

// ---- Publishers ----

void RunPublisher(int id, const Options& o,
                   const std::vector<uint8_t>* payload,
                   std::atomic<bool>* stop) {
  auto node = talos::Node::Create("bench_pub_" + std::to_string(id));
  auto pub = node->Advertise<talos::msgs::CompressedImage>(
      o.topic_prefix + std::to_string(id));

  talos::msgs::CompressedImage msg;
  msg.header.frame_id = "cam_" + std::to_string(id);
  msg.format = "png";
  msg.data = *payload;  // copy once; zenoh takes its own copy on Publish

  const auto period = std::chrono::nanoseconds(
      static_cast<long long>(1e9 / o.hz));
  auto next = clock::now();
  uint64_t seq = 0;
  while (!stop->load() && talos::Ok()) {
    uint64_t ns = NowNs();
    msg.header.stamp.sec = static_cast<int32_t>(ns / 1'000'000'000ULL);
    msg.header.stamp.nanosec = static_cast<uint32_t>(ns % 1'000'000'000ULL);
    // Stuff the sequence number into frame_id so the subscriber can also
    // detect drops.
    msg.header.frame_id = "cam_" + std::to_string(id) + "#" + std::to_string(seq++);
    pub.Publish(msg);
    next += period;
    std::this_thread::sleep_until(next);
  }
}

// ---- Subscribers ----

void StartSubscribers(
    std::shared_ptr<talos::Node>& node_owner,
    const Options& o,
    TopicStatsVec& stats,
    std::vector<talos::Subscription>& subs) {
  node_owner = talos::Node::Create("bench_sub");
  for (int i = 0; i < o.topics; ++i) {
    auto entry = std::make_unique<TopicStats>();
    entry->topic = o.topic_prefix + std::to_string(i);
    entry->window_cap = o.window;
    TopicStats* sp = entry.get();
    subs.push_back(node_owner->Subscribe<talos::msgs::CompressedImage>(
        entry->topic,
        [sp](const talos::msgs::CompressedImage& msg) {
          const uint64_t now = NowNs();
          const uint64_t sent =
              static_cast<uint64_t>(msg.header.stamp.sec) * 1'000'000'000ULL
              + msg.header.stamp.nanosec;
          const uint64_t lat = (now > sent) ? (now - sent) : 0;
          sp->received.fetch_add(1, std::memory_order_relaxed);
          sp->bytes.fetch_add(msg.data.size(), std::memory_order_relaxed);
          PushSample(*sp, lat);
        }));
    stats.push_back(std::move(entry));
  }
}

}  // namespace

int main(int argc, char** argv) {
  auto o = ParseArgs(argc, argv);
  talos::Init(argc, argv);

  std::vector<uint8_t> payload;
  if (o.role == "pub" || o.role == "both") {
    payload = LoadPayload(o);
    TALOS_LOG(INFO) << "payload size = " << payload.size() << " bytes";
  }

  std::atomic<bool> stop_pub{false};
  std::vector<std::thread> pub_threads;
  if (o.role == "pub" || o.role == "both") {
    for (int i = 0; i < o.topics; ++i) {
      pub_threads.emplace_back(RunPublisher, i, std::ref(o),
                                 &payload, &stop_pub);
    }
    TALOS_LOG(INFO) << "started " << o.topics
                    << " publishers @ " << o.hz << " Hz";
  }

  std::shared_ptr<talos::Node> sub_node;
  TopicStatsVec stats;
  std::vector<talos::Subscription> subs;
  if (o.role == "sub" || o.role == "both") {
    StartSubscribers(sub_node, o, stats, subs);
    TALOS_LOG(INFO) << "started " << o.topics << " subscribers";
  }

  // Reporting loop — only meaningful on subscriber side.
  const auto deadline = (o.duration_s > 0)
      ? (clock::now() + std::chrono::duration_cast<clock::duration>(
                          std::chrono::duration<double>(o.duration_s)))
      : clock::time_point::max();

  auto next_report = clock::now() +
      std::chrono::duration_cast<clock::duration>(
          std::chrono::duration<double>(o.report_s));

  while (talos::Ok() && clock::now() < deadline) {
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    if (!stats.empty() && clock::now() >= next_report) {
      Report(stats, o.report_s);
      next_report += std::chrono::duration_cast<clock::duration>(
          std::chrono::duration<double>(o.report_s));
    }
  }

  stop_pub.store(true);
  for (auto& t : pub_threads) if (t.joinable()) t.join();
  if (!stats.empty()) Report(stats, o.report_s);
  return 0;
}
