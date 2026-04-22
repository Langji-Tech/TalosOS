#ifndef TALOSOS_TIMER_H_
#define TALOSOS_TIMER_H_

// 周期 / 一次性回调定时器 —— 头文件实现，后台线程驱动，RAII 析构时自动
// cancel + join，不泄漏。与 ROS1 `ros::Timer` 用法类似：
//
//   talos::Timer t(0.1, [] { TALOS_LOG(INFO) << "tick"; });   // 10 Hz
//   talos::Timer one(std::chrono::seconds(3),
//                      [] { TALOS_LOG(INFO) << "one-shot"; }, /*oneshot=*/true);
//
// Cancel 可显式调；析构会兜底。回调里抛异常会被吞并打到 stderr（不会
// 杀掉定时器线程）。

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <exception>
#include <functional>
#include <iostream>
#include <memory>
#include <mutex>
#include <thread>
#include <utility>

namespace talos {

class Timer {
 public:
  using Callback = std::function<void()>;
  using nanos    = std::chrono::nanoseconds;

  Timer() = default;

  Timer(nanos period, Callback cb, bool oneshot = false)
      : impl_(std::make_unique<Impl>(period, std::move(cb), oneshot)) {}

  /// 便捷构造：按 Hz 指定。0 或负值视为不启动（构造完立即 cancel）。
  Timer(double hz, Callback cb, bool oneshot = false)
      : Timer(hz > 0.0
                ? std::chrono::duration_cast<nanos>(
                      std::chrono::duration<double>(1.0 / hz))
                : nanos::zero(),
              std::move(cb), oneshot) {
    if (!(hz > 0.0)) Cancel();
  }

  /// `std::chrono::duration<Rep, Period>` 任意单位的便捷构造
  template <class Rep, class Period>
  Timer(std::chrono::duration<Rep, Period> period, Callback cb,
        bool oneshot = false)
      : Timer(std::chrono::duration_cast<nanos>(period),
              std::move(cb), oneshot) {}

  ~Timer() { Cancel(); }

  Timer(Timer&&) noexcept = default;
  Timer& operator=(Timer&& rhs) noexcept {
    Cancel();
    impl_ = std::move(rhs.impl_);
    return *this;
  }

  Timer(const Timer&) = delete;
  Timer& operator=(const Timer&) = delete;

  /// 停止并 join 后台线程。多次调用安全、幂等。
  void Cancel() { if (impl_) impl_->Cancel(); }

  bool valid() const { return impl_ && impl_->valid(); }

 private:
  class Impl {
   public:
    Impl(nanos period, Callback cb, bool oneshot)
        : period_(period), cb_(std::move(cb)), oneshot_(oneshot) {
      if (period_.count() > 0 && cb_) {
        thread_ = std::thread([this] { Run(); });
      }
    }

    ~Impl() { Cancel(); }

    void Cancel() {
      {
        std::lock_guard<std::mutex> lk(mu_);
        if (cancelled_) return;
        cancelled_ = true;
      }
      cv_.notify_all();
      if (thread_.joinable() &&
          thread_.get_id() != std::this_thread::get_id()) {
        thread_.join();
      }
    }

    bool valid() const { return period_.count() > 0 && cb_; }

   private:
    void Run() {
      auto next = std::chrono::steady_clock::now() + period_;
      while (true) {
        std::unique_lock<std::mutex> lk(mu_);
        if (cv_.wait_until(lk, next, [this] { return cancelled_; })) {
          return;
        }
        lk.unlock();
        try {
          cb_();
        } catch (const std::exception& ex) {
          std::cerr << "talos::Timer callback threw: " << ex.what() << "\n";
        } catch (...) {
          std::cerr << "talos::Timer callback threw non-std exception\n";
        }
        if (oneshot_) return;
        next += period_;
      }
    }

    nanos period_;
    Callback cb_;
    bool oneshot_;

    std::mutex mu_;
    std::condition_variable cv_;
    bool cancelled_ = false;
    std::thread thread_;
  };

  std::unique_ptr<Impl> impl_;
};

}  // namespace talos

#endif  // TALOSOS_TIMER_H_
