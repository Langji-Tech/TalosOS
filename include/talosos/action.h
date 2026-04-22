#ifndef TALOSOS_ACTION_H_
#define TALOSOS_ACTION_H_

#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <random>
#include <string>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>

#include "talosos/logging.h"
#include "talosos/node.h"
#include "talosos/serialization.h"

namespace talos {

// 128-bit goal identifier. Printed as 32-char hex.
struct GoalID {
  std::array<uint8_t, 16> uuid{};

  bool operator==(const GoalID& o) const { return uuid == o.uuid; }
  bool operator!=(const GoalID& o) const { return !(*this == o); }
  bool operator<(const GoalID& o) const { return uuid < o.uuid; }

  std::string ToString() const {
    static const char* kHex = "0123456789abcdef";
    std::string s;
    s.reserve(32);
    for (uint8_t b : uuid) {
      s.push_back(kHex[b >> 4]);
      s.push_back(kHex[b & 0xF]);
    }
    return s;
  }
};

inline void Write(cdr::Writer& w, const GoalID& id) { cdr::Write(w, id.uuid); }
inline void Read(cdr::Reader& r, GoalID& id) { cdr::Read(r, id.uuid); }

inline GoalID NewGoalID() {
  thread_local std::random_device rd;
  thread_local std::mt19937_64 rng{rd()};
  GoalID id;
  auto write_u64 = [&](size_t offset) {
    uint64_t v = rng();
    for (size_t i = 0; i < 8; ++i) {
      id.uuid[offset + i] = static_cast<uint8_t>((v >> (i * 8)) & 0xFF);
    }
  };
  write_u64(0);
  write_u64(8);
  // RFC 4122 variant/version bits (use v4 random).
  id.uuid[6] = static_cast<uint8_t>((id.uuid[6] & 0x0F) | 0x40);
  id.uuid[8] = static_cast<uint8_t>((id.uuid[8] & 0x3F) | 0x80);
  return id;
}

enum class GoalStatus : int32_t {
  kUnknown   = 0,
  kAccepted  = 1,
  kExecuting = 2,
  kCanceling = 3,
  kSucceeded = 4,
  kAborted   = 5,
  kCanceled  = 6,
  kRejected  = 7,
};

inline const char* ToString(GoalStatus s) {
  switch (s) {
    case GoalStatus::kUnknown:   return "unknown";
    case GoalStatus::kAccepted:  return "accepted";
    case GoalStatus::kExecuting: return "executing";
    case GoalStatus::kCanceling: return "canceling";
    case GoalStatus::kSucceeded: return "succeeded";
    case GoalStatus::kAborted:   return "aborted";
    case GoalStatus::kCanceled:  return "canceled";
    case GoalStatus::kRejected:  return "rejected";
  }
  return "invalid";
}

// ---- Wire envelopes (generic wrappers over user types) ----

template <typename Goal>
struct ActionGoalMsg {
  GoalID id;
  Goal goal;
  TALOS_MESSAGE_FIELDS(id, goal)
};

template <typename Feedback>
struct ActionFeedbackMsg {
  GoalID id;
  Feedback feedback;
  TALOS_MESSAGE_FIELDS(id, feedback)
};

template <typename Result>
struct ActionResultMsg {
  GoalID id;
  int32_t status = static_cast<int32_t>(GoalStatus::kUnknown);
  Result result;
  TALOS_MESSAGE_FIELDS(id, status, result)
};

struct ActionCancelMsg {
  GoalID id;
  TALOS_MESSAGE_FIELDS(id)
};

// ---- Server ----

template <typename Goal, typename Feedback, typename Result>
class ActionServer {
 public:
  class Handle {
   public:
    Handle(GoalID id, Goal goal, std::shared_ptr<std::atomic<bool>> cancel_flag,
           std::function<void(const Feedback&)> publish_feedback)
        : id_(std::move(id)),
          goal_(std::move(goal)),
          cancel_flag_(std::move(cancel_flag)),
          publish_feedback_(std::move(publish_feedback)) {}

    const GoalID& id() const { return id_; }
    const Goal& goal() const { return goal_; }
    bool canceling() const { return cancel_flag_->load(); }

    void PublishFeedback(const Feedback& fb) { publish_feedback_(fb); }

   private:
    GoalID id_;
    Goal goal_;
    std::shared_ptr<std::atomic<bool>> cancel_flag_;
    std::function<void(const Feedback&)> publish_feedback_;
  };

  using ExecuteFn = std::function<
      std::pair<GoalStatus, Result>(Handle&)>;

  ActionServer() = default;

  ActionServer(std::shared_ptr<Node> node, std::string name,
                ExecuteFn execute_fn)
      : state_(std::make_shared<State>()) {
    state_->name = std::move(name);
    state_->execute = std::move(execute_fn);
    state_->node = node;

    state_->feedback_pub =
        node->template Advertise<ActionFeedbackMsg<Feedback>>(state_->name + "/feedback");
    state_->result_pub =
        node->template Advertise<ActionResultMsg<Result>>(state_->name + "/result");

    auto weak = std::weak_ptr<State>(state_);

    state_->goal_sub = node->template Subscribe<ActionGoalMsg<Goal>>(
        state_->name + "/goal",
        [weak](const ActionGoalMsg<Goal>& msg) {
          auto self = weak.lock();
          if (!self) return;
          self->HandleGoal(msg);
        });

    state_->cancel_sub = node->template Subscribe<ActionCancelMsg>(
        state_->name + "/cancel",
        [weak](const ActionCancelMsg& msg) {
          auto self = weak.lock();
          if (!self) return;
          self->HandleCancel(msg);
        });
  }

  ~ActionServer() {
    if (!state_) return;
    state_->shutting_down.store(true);
    std::vector<std::thread> workers;
    {
      std::lock_guard<std::mutex> lock(state_->mu);
      for (auto& [id, entry] : state_->active) {
        entry.cancel_flag->store(true);
      }
      workers = std::move(state_->workers);
    }
    for (auto& t : workers) if (t.joinable()) t.join();
  }

  ActionServer(const ActionServer&) = delete;
  ActionServer& operator=(const ActionServer&) = delete;
  ActionServer(ActionServer&&) noexcept = default;
  ActionServer& operator=(ActionServer&&) noexcept = default;

  const std::string& name() const {
    static const std::string kEmpty;
    return state_ ? state_->name : kEmpty;
  }

 private:
  struct ActiveEntry {
    std::shared_ptr<std::atomic<bool>> cancel_flag;
  };

  struct State {
    std::string name;
    std::shared_ptr<Node> node;
    ExecuteFn execute;
    Publisher feedback_pub;
    Publisher result_pub;
    Subscription goal_sub;
    Subscription cancel_sub;

    std::mutex mu;
    std::unordered_map<std::string, ActiveEntry> active;
    std::vector<std::thread> workers;
    std::atomic<bool> shutting_down{false};

    void HandleGoal(ActionGoalMsg<Goal> msg) {
      if (shutting_down.load()) return;

      auto cancel_flag = std::make_shared<std::atomic<bool>>(false);
      const std::string key = msg.id.ToString();

      {
        std::lock_guard<std::mutex> lock(mu);
        if (active.count(key)) {
          TALOS_WARN_NAMED("action", "duplicate goal %s ignored", key.c_str());
          return;
        }
        active[key] = ActiveEntry{cancel_flag};
      }

      TALOS_INFO_NAMED("action", "goal %s accepted", key.c_str());

      auto self_weak = std::weak_ptr<State>(shared_from_this_or_null());
      auto worker = std::thread([this_state = self_weak, id = msg.id,
                                  goal = std::move(msg.goal), cancel_flag]() {
        auto s = this_state.lock();
        if (!s) return;

        auto publish_fb = [s, id](const Feedback& fb) {
          ActionFeedbackMsg<Feedback> env;
          env.id = id;
          env.feedback = fb;
          s->feedback_pub.Publish(env);
        };

        Handle handle(id, std::move(goal), cancel_flag, std::move(publish_fb));

        GoalStatus final_status = GoalStatus::kAborted;
        Result result{};
        try {
          auto out = s->execute(handle);
          final_status = out.first;
          result = std::move(out.second);
        } catch (const std::exception& ex) {
          TALOS_ERROR_NAMED("action", "execute threw: %s", ex.what());
        } catch (...) {
          TALOS_ERROR_NAMED("action", "execute threw unknown");
        }

        ActionResultMsg<Result> env;
        env.id = id;
        env.status = static_cast<int32_t>(final_status);
        env.result = std::move(result);
        s->result_pub.Publish(env);

        std::lock_guard<std::mutex> lock(s->mu);
        s->active.erase(id.ToString());
      });
      {
        std::lock_guard<std::mutex> lock(mu);
        workers.push_back(std::move(worker));
      }
    }

    void HandleCancel(const ActionCancelMsg& msg) {
      const std::string key = msg.id.ToString();
      std::lock_guard<std::mutex> lock(mu);
      auto it = active.find(key);
      if (it != active.end()) {
        TALOS_INFO_NAMED("action", "cancel request %s", key.c_str());
        it->second.cancel_flag->store(true);
      }
    }

    std::shared_ptr<State> shared_from_this_or_null() {
      return shared_self.lock();
    }

    std::weak_ptr<State> shared_self;
  };

  std::shared_ptr<State> state_;

  friend class ActionServerBuilder;

 public:
  // Idiom: the weak-from-this is set after construction.
  void Finalize() {
    if (state_) state_->shared_self = state_;
  }
};

// ---- Client ----

template <typename Goal, typename Feedback, typename Result>
class ActionClient {
 public:
  class GoalHandle {
   public:
    using FeedbackCb = std::function<void(const Feedback&)>;

    GoalHandle() = default;
    const GoalID& id() const { return id_; }

    bool WaitForResult(std::chrono::milliseconds timeout, Result& out,
                        GoalStatus& status) {
      std::unique_lock<std::mutex> lock(state_->mu);
      if (!state_->cv.wait_for(lock, timeout,
                                 [&]() { return state_->has_result; })) {
        return false;
      }
      out = state_->result;
      status = state_->status;
      return true;
    }

    bool WaitForResult(Result& out, GoalStatus& status) {
      std::unique_lock<std::mutex> lock(state_->mu);
      state_->cv.wait(lock, [&]() { return state_->has_result; });
      out = state_->result;
      status = state_->status;
      return true;
    }

    void Cancel() {
      ActionCancelMsg msg;
      msg.id = id_;
      state_->cancel_pub->Publish(msg);
    }

    void SetFeedbackCallback(FeedbackCb cb) {
      std::lock_guard<std::mutex> lock(state_->mu);
      state_->feedback_cb = std::move(cb);
    }

   private:
    friend class ActionClient;

    struct State {
      std::mutex mu;
      std::condition_variable cv;
      bool has_result = false;
      Result result{};
      GoalStatus status = GoalStatus::kUnknown;
      FeedbackCb feedback_cb;
      Publisher* cancel_pub = nullptr;
    };

    GoalID id_{};
    std::shared_ptr<State> state_;
  };

  ActionClient() = default;

  ActionClient(std::shared_ptr<Node> node, std::string name)
      : state_(std::make_shared<State>()) {
    state_->name = std::move(name);
    state_->goal_pub =
        node->template Advertise<ActionGoalMsg<Goal>>(state_->name + "/goal");
    state_->cancel_pub =
        node->template Advertise<ActionCancelMsg>(state_->name + "/cancel");

    auto weak = std::weak_ptr<State>(state_);

    state_->feedback_sub = node->template Subscribe<ActionFeedbackMsg<Feedback>>(
        state_->name + "/feedback",
        [weak](const ActionFeedbackMsg<Feedback>& msg) {
          auto self = weak.lock();
          if (!self) return;
          std::shared_ptr<typename GoalHandle::State> target;
          typename GoalHandle::FeedbackCb cb;
          {
            std::lock_guard<std::mutex> lock(self->mu);
            auto it = self->handles.find(msg.id.ToString());
            if (it == self->handles.end()) return;
            target = it->second;
          }
          {
            std::lock_guard<std::mutex> lock(target->mu);
            cb = target->feedback_cb;
          }
          if (cb) cb(msg.feedback);
        });

    state_->result_sub = node->template Subscribe<ActionResultMsg<Result>>(
        state_->name + "/result",
        [weak](const ActionResultMsg<Result>& msg) {
          auto self = weak.lock();
          if (!self) return;
          std::shared_ptr<typename GoalHandle::State> target;
          {
            std::lock_guard<std::mutex> lock(self->mu);
            auto it = self->handles.find(msg.id.ToString());
            if (it == self->handles.end()) return;
            target = it->second;
            self->handles.erase(it);
          }
          {
            std::lock_guard<std::mutex> lock(target->mu);
            target->result = msg.result;
            target->status = static_cast<GoalStatus>(msg.status);
            target->has_result = true;
          }
          target->cv.notify_all();
        });
  }

  const std::string& name() const {
    static const std::string kEmpty;
    return state_ ? state_->name : kEmpty;
  }

  std::shared_ptr<GoalHandle> SendGoal(
      const Goal& goal,
      typename GoalHandle::FeedbackCb feedback_cb = nullptr) {
    auto handle = std::make_shared<GoalHandle>();
    handle->id_ = NewGoalID();
    handle->state_ = std::make_shared<typename GoalHandle::State>();
    handle->state_->feedback_cb = std::move(feedback_cb);
    handle->state_->cancel_pub = &state_->cancel_pub;

    {
      std::lock_guard<std::mutex> lock(state_->mu);
      state_->handles[handle->id_.ToString()] = handle->state_;
    }

    ActionGoalMsg<Goal> env;
    env.id = handle->id_;
    env.goal = goal;
    state_->goal_pub.Publish(env);

    TALOS_DEBUG_NAMED("action", "sent goal %s", handle->id_.ToString().c_str());
    return handle;
  }

 private:
  struct State {
    std::string name;
    Publisher goal_pub;
    Publisher cancel_pub;
    Subscription feedback_sub;
    Subscription result_sub;

    std::mutex mu;
    std::unordered_map<std::string,
                         std::shared_ptr<typename GoalHandle::State>> handles;
  };

  std::shared_ptr<State> state_;
};

// ---- Factory helpers ----

template <typename Goal, typename Feedback, typename Result>
ActionServer<Goal, Feedback, Result> MakeActionServer(
    std::shared_ptr<Node> node, const std::string& name,
    typename ActionServer<Goal, Feedback, Result>::ExecuteFn execute) {
  ActionServer<Goal, Feedback, Result> server(node, name, std::move(execute));
  server.Finalize();
  return server;
}

template <typename Goal, typename Feedback, typename Result>
ActionClient<Goal, Feedback, Result> MakeActionClient(
    std::shared_ptr<Node> node, const std::string& name) {
  return ActionClient<Goal, Feedback, Result>(node, name);
}

}  // namespace talos

#endif  // TALOSOS_ACTION_H_
