#ifndef TALOSOS_LOGGING_H_
#define TALOSOS_LOGGING_H_

#include <cstdio>
#include <ostream>
#include <sstream>
#include <string>
#include <string_view>
#include <utility>

namespace talos {

enum class LogSeverity : int {
  kDebug = 0,
  kInfo = 1,
  kWarn = 2,
  kError = 3,
  kFatal = 4,
};

void SetLogSeverity(LogSeverity s);
LogSeverity GetLogSeverity();

void SetLogUseColor(bool enabled);

void LogImpl(LogSeverity severity,
             std::string_view source,
             std::string_view file,
             int line,
             std::string_view message);

inline std::string LogFormat(const char* fmt) { return fmt ? fmt : ""; }

template <typename... Args>
std::string LogFormat(const char* fmt, Args... args) {
  if (!fmt) return "";
#if defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wformat-security"
#pragma GCC diagnostic ignored "-Wformat-nonliteral"
#endif
  int n = std::snprintf(nullptr, 0, fmt, args...);
  if (n < 0) return "";
  std::string out(static_cast<size_t>(n), '\0');
  std::snprintf(out.data(), static_cast<size_t>(n) + 1, fmt, args...);
#if defined(__GNUC__)
#pragma GCC diagnostic pop
#endif
  return out;
}

// ---- glog / absl-style iostream logging ----
//
// Use as:   TALOS_LOG(INFO) << "hello " << name << " count=" << count;
//
// Implemented as a short-lived stack object whose destructor flushes once to
// LogImpl. The severity short-circuit below ensures `TALOS_LOG(DEBUG) << ...`
// compiles to a no-op when the current severity excludes it — no allocation,
// no formatting.
class LogMessage {
 public:
  LogMessage(LogSeverity severity, const char* file, int line,
             std::string_view source = {})
      : severity_(severity), file_(file), line_(line), source_(source) {}

  ~LogMessage() noexcept {
    try {
      LogImpl(severity_, source_, file_, line_, stream_.str());
    } catch (...) {
      // Never let a log call escape — logging must not cause a terminate.
    }
  }

  LogMessage(const LogMessage&) = delete;
  LogMessage& operator=(const LogMessage&) = delete;

  std::ostream& stream() { return stream_; }

 private:
  LogSeverity severity_;
  const char* file_;
  int line_;
  std::string_view source_;
  std::ostringstream stream_;
};

// Voidify: `LogVoidify() & some_ostream&` collapses to void so it can be used
// on the right-hand side of a ternary whose other branch is `(void)0`.
class LogVoidify {
 public:
  LogVoidify() = default;
  // Precedence: `<<` binds tighter than `&`, so `stream << x` runs first.
  void operator&(std::ostream&) const {}
};

inline bool LogEnabled(LogSeverity s) {
  return static_cast<int>(GetLogSeverity()) <= static_cast<int>(s);
}

}  // namespace talos

#define TALOSOS_LOG_(sev, source, ...)                                          \
  do {                                                                          \
    if (static_cast<int>(::talos::GetLogSeverity()) <= static_cast<int>(sev)) { \
      ::talos::LogImpl((sev), (source), __FILE__, __LINE__,                     \
                       ::talos::LogFormat(__VA_ARGS__));                        \
    }                                                                           \
  } while (0)

#define TALOS_DEBUG(...) TALOSOS_LOG_(::talos::LogSeverity::kDebug, "", __VA_ARGS__)
#define TALOS_INFO(...)  TALOSOS_LOG_(::talos::LogSeverity::kInfo,  "", __VA_ARGS__)
#define TALOS_WARN(...)  TALOSOS_LOG_(::talos::LogSeverity::kWarn,  "", __VA_ARGS__)
#define TALOS_ERROR(...) TALOSOS_LOG_(::talos::LogSeverity::kError, "", __VA_ARGS__)
#define TALOS_FATAL(...) TALOSOS_LOG_(::talos::LogSeverity::kFatal, "", __VA_ARGS__)

#define TALOS_DEBUG_NAMED(name, ...) TALOSOS_LOG_(::talos::LogSeverity::kDebug, name, __VA_ARGS__)
#define TALOS_INFO_NAMED(name, ...)  TALOSOS_LOG_(::talos::LogSeverity::kInfo,  name, __VA_ARGS__)
#define TALOS_WARN_NAMED(name, ...)  TALOSOS_LOG_(::talos::LogSeverity::kWarn,  name, __VA_ARGS__)
#define TALOS_ERROR_NAMED(name, ...) TALOSOS_LOG_(::talos::LogSeverity::kError, name, __VA_ARGS__)
#define TALOS_FATAL_NAMED(name, ...) TALOSOS_LOG_(::talos::LogSeverity::kFatal, name, __VA_ARGS__)

#define TALOSOS_LOG_STREAM_(sev, source, expr)                                  \
  do {                                                                          \
    if (static_cast<int>(::talos::GetLogSeverity()) <= static_cast<int>(sev)) { \
      std::ostringstream _talos_log_ss;                                         \
      _talos_log_ss << expr;                                                    \
      ::talos::LogImpl((sev), (source), __FILE__, __LINE__,                     \
                       _talos_log_ss.str());                                    \
    }                                                                           \
  } while (0)

#define TALOS_DEBUG_STREAM(expr) TALOSOS_LOG_STREAM_(::talos::LogSeverity::kDebug, "", expr)
#define TALOS_INFO_STREAM(expr)  TALOSOS_LOG_STREAM_(::talos::LogSeverity::kInfo,  "", expr)
#define TALOS_WARN_STREAM(expr)  TALOSOS_LOG_STREAM_(::talos::LogSeverity::kWarn,  "", expr)
#define TALOS_ERROR_STREAM(expr) TALOSOS_LOG_STREAM_(::talos::LogSeverity::kError, "", expr)
#define TALOS_FATAL_STREAM(expr) TALOSOS_LOG_STREAM_(::talos::LogSeverity::kFatal, "", expr)

// ---- TALOS_LOG(LEVEL) << ... chained iostream form ----
//
//   TALOS_LOG(INFO)       << "count=" << count;
//   TALOS_LOG(WARN)       << "slow loop: " << dt_ms << " ms";
//   TALOS_LOG_NAMED(INFO, "camera") << "frame size=" << bytes;
//
// The level name must be one of DEBUG / INFO / WARN / ERROR / FATAL.
#define TALOSOS_SEVERITY_DEBUG ::talos::LogSeverity::kDebug
#define TALOSOS_SEVERITY_INFO  ::talos::LogSeverity::kInfo
#define TALOSOS_SEVERITY_WARN  ::talos::LogSeverity::kWarn
#define TALOSOS_SEVERITY_ERROR ::talos::LogSeverity::kError
#define TALOSOS_SEVERITY_FATAL ::talos::LogSeverity::kFatal

#define TALOS_LOG(LEVEL)                                                      \
  (!::talos::LogEnabled(TALOSOS_SEVERITY_##LEVEL))                             \
      ? (void)0                                                                \
      : ::talos::LogVoidify() &                                                \
        ::talos::LogMessage(TALOSOS_SEVERITY_##LEVEL,                          \
                            __FILE__, __LINE__).stream()

#define TALOS_LOG_NAMED(LEVEL, NAME)                                          \
  (!::talos::LogEnabled(TALOSOS_SEVERITY_##LEVEL))                             \
      ? (void)0                                                                \
      : ::talos::LogVoidify() &                                                \
        ::talos::LogMessage(TALOSOS_SEVERITY_##LEVEL,                          \
                            __FILE__, __LINE__, (NAME)).stream()

#endif  // TALOSOS_LOGGING_H_