#ifndef TALOSOS_RATE_H_
#define TALOSOS_RATE_H_

// 定频循环 + 秒表 + tic/toc —— 纯头文件，与 ROS1 `ros::Rate` / `ros::WallRate`
// 使用习惯保持一致，但走 `std::chrono::steady_clock`，不会被系统时钟跳变
// 干扰。
//
// 用法：
//   talos::Rate r(50.0);            // 50 Hz
//   while (talos::Ok()) {
//     do_work();
//     if (!r.Sleep()) TALOS_WARN("fell behind by %.1f ms",
//                                  (r.cycle_time().count() - r.period().count()) / 1e6);
//   }

#include <chrono>
#include <thread>
#include <string>

#include "talosos/logging.h"

namespace talos {

// ---------------------------------------------------------------------------
// Rate —— 定频循环睡眠器
// ---------------------------------------------------------------------------

class Rate {
 public:
  using clock = std::chrono::steady_clock;
  using nanos = std::chrono::nanoseconds;

  explicit Rate(double hz)
      : period_(std::chrono::duration_cast<nanos>(
            std::chrono::duration<double>(1.0 / hz))) {
    Reset();
  }

  explicit Rate(nanos period) : period_(period) { Reset(); }

  /// 把内部"上次唤醒时刻"重置为 now()。长时间初始化后调一次可以避免
  /// 第一次 Sleep() 睡一个很大的时间差。
  void Reset() { last_ = clock::now(); }

  /// 睡到下一个周期点。如果这一轮已经超时（落后于计划），不再睡，
  /// 返回 `false`；否则睡满剩余时间并返回 `true`。
  /// `cycle_time()` 在调用之后反映上一轮实际花费。
  bool Sleep() {
    const auto now = clock::now();
    const auto next = last_ + period_;
    if (now < next) {
      std::this_thread::sleep_until(next);
      cycle_ = std::chrono::duration_cast<nanos>(next - last_);
      last_ = next;
      return true;
    }
    cycle_ = std::chrono::duration_cast<nanos>(now - last_);
    last_ = now;
    return false;
  }

  double hz() const {
    return period_.count() == 0 ? 0.0 : 1e9 / static_cast<double>(period_.count());
  }
  nanos period() const { return period_; }
  nanos cycle_time() const { return cycle_; }

 private:
  nanos period_;
  clock::time_point last_;
  nanos cycle_{0};
};

// ---------------------------------------------------------------------------
// Stopwatch —— 常规秒表，RAII 起点
// ---------------------------------------------------------------------------

class Stopwatch {
 public:
  using clock = std::chrono::steady_clock;

  Stopwatch() { Reset(); }

  void Reset() { start_ = clock::now(); }

  std::chrono::nanoseconds elapsed() const { return clock::now() - start_; }
  double seconds()      const { return std::chrono::duration<double>(elapsed()).count(); }
  double milliseconds() const { return seconds() * 1000.0; }
  double microseconds() const { return seconds() * 1e6; }

 private:
  clock::time_point start_;
};

// ---------------------------------------------------------------------------
// Tic / Toc —— MATLAB 风格快速计时（每线程独立）
// ---------------------------------------------------------------------------

namespace detail {
inline std::chrono::steady_clock::time_point& _tic_point() {
  thread_local std::chrono::steady_clock::time_point t =
      std::chrono::steady_clock::now();
  return t;
}
}  // namespace detail

/// 记录当前时刻作为 tic 点（每线程独立）。
inline void Tic() { detail::_tic_point() = std::chrono::steady_clock::now(); }

/// 返回自最近一次 `Tic()` 以来的秒数，**不**重置 tic 点。
inline double Toc() {
  return std::chrono::duration<double>(
           std::chrono::steady_clock::now() - detail::_tic_point()).count();
}

/// `Toc()` 后顺手 `Tic()`：拿完时长，重置基准。
inline double TocReset() {
  const double s = Toc();
  Tic();
  return s;
}

// ---------------------------------------------------------------------------
// ScopedTimer —— RAII，析构时打印 "[label] X.X ms"
// ---------------------------------------------------------------------------

class ScopedTimer {
 public:
  explicit ScopedTimer(std::string label) : label_(std::move(label)) {}
  ~ScopedTimer() {
    TALOS_LOG(INFO) << "[" << label_ << "] "
                    << sw_.milliseconds() << " ms";
  }
  // 禁拷贝/移动，避免提前析构
  ScopedTimer(const ScopedTimer&) = delete;
  ScopedTimer& operator=(const ScopedTimer&) = delete;

  double milliseconds() const { return sw_.milliseconds(); }

 private:
  std::string label_;
  Stopwatch sw_;
};

// 最小宏：`TALOS_SCOPED_TIMER("load image");`
#define TALOS_SCOPED_TIMER(LABEL)                                        \
  ::talos::ScopedTimer _talos_scoped_timer_##__LINE__((LABEL))

}  // namespace talos

#endif  // TALOSOS_RATE_H_
