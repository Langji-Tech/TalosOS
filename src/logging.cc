#include "talosos/logging.h"

#if defined(_WIN32)
#  include <io.h>
#  include <windows.h>
#  define TALOSOS_ISATTY(fd)  ::_isatty(fd)
#  define TALOSOS_FILENO(fp)  ::_fileno(fp)
#else
#  include <unistd.h>
#  define TALOSOS_ISATTY(fd)  ::isatty(fd)
#  define TALOSOS_FILENO(fp)  ::fileno(fp)
#endif

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <mutex>
#include <string>

namespace talos {
namespace {

std::atomic<int> g_severity{static_cast<int>(LogSeverity::kInfo)};
std::atomic<int> g_use_color{-1};
std::mutex g_log_mutex;

bool ShouldUseColor() {
  int cached = g_use_color.load();
  if (cached >= 0) return cached != 0;

  bool enable = TALOSOS_ISATTY(TALOSOS_FILENO(stderr)) != 0;

#if defined(_WIN32)
  // Windows consoles need VT sequence opt-in before ANSI colors work.
  if (enable) {
    HANDLE h = ::GetStdHandle(STD_ERROR_HANDLE);
    DWORD mode = 0;
    if (h == INVALID_HANDLE_VALUE || !::GetConsoleMode(h, &mode) ||
        !::SetConsoleMode(h, mode | ENABLE_VIRTUAL_TERMINAL_PROCESSING)) {
      enable = false;
    }
  }
#endif

  if (const char* v = std::getenv("TALOS_LOG_COLOR")) {
    if (std::strcmp(v, "0") == 0 || std::strcmp(v, "false") == 0) enable = false;
    else if (std::strcmp(v, "1") == 0 || std::strcmp(v, "true") == 0) enable = true;
  }
  if (const char* v = std::getenv("NO_COLOR")) {
    if (v[0] != '\0') enable = false;
  }
  g_use_color.store(enable ? 1 : 0);
  return enable;
}

const char* ColorFor(LogSeverity s) {
  switch (s) {
    case LogSeverity::kDebug: return "\x1b[36m";          // cyan
    case LogSeverity::kInfo:  return "\x1b[32m";          // green
    case LogSeverity::kWarn:  return "\x1b[33m";          // yellow
    case LogSeverity::kError: return "\x1b[31m";          // red
    case LogSeverity::kFatal: return "\x1b[1;41;97m";     // bold white-on-red
  }
  return "";
}

const char* TagFor(LogSeverity s) {
  switch (s) {
    case LogSeverity::kDebug: return "DEBUG";
    case LogSeverity::kInfo:  return "INFO ";
    case LogSeverity::kWarn:  return "WARN ";
    case LogSeverity::kError: return "ERROR";
    case LogSeverity::kFatal: return "FATAL";
  }
  return "?????";
}

std::string NowTimestamp() {
  using namespace std::chrono;
  auto now = system_clock::now();
  auto secs = time_point_cast<seconds>(now);
  auto ms = duration_cast<milliseconds>(now - secs).count();
  std::time_t t = system_clock::to_time_t(secs);
  std::tm tm{};
#if defined(_WIN32)
  // MSVC / mingw: ::localtime_s(tm*, time_t*). Argument order reversed
  // from POSIX.
  ::localtime_s(&tm, &t);
#else
  ::localtime_r(&t, &tm);
#endif
  char buf[32];
  std::snprintf(buf, sizeof(buf), "%02d:%02d:%02d.%03lld",
                tm.tm_hour, tm.tm_min, tm.tm_sec,
                static_cast<long long>(ms));
  return buf;
}

}  // namespace

void SetLogSeverity(LogSeverity s) {
  g_severity.store(static_cast<int>(s));
}

LogSeverity GetLogSeverity() {
  return static_cast<LogSeverity>(g_severity.load());
}

void SetLogUseColor(bool enabled) {
  g_use_color.store(enabled ? 1 : 0);
}

void LogImpl(LogSeverity severity,
             std::string_view source,
             std::string_view file,
             int line,
             std::string_view message) {
  const bool color = ShouldUseColor();
  const char* color_on = color ? ColorFor(severity) : "";
  const char* color_off = color ? "\x1b[0m" : "";
  const std::string ts = NowTimestamp();

  std::lock_guard<std::mutex> lock(g_log_mutex);
  if (!source.empty()) {
    std::fprintf(stderr, "%s[%s %s] [%.*s]%s %.*s (%.*s:%d)\n",
                 color_on, TagFor(severity), ts.c_str(),
                 static_cast<int>(source.size()), source.data(),
                 color_off,
                 static_cast<int>(message.size()), message.data(),
                 static_cast<int>(file.size()), file.data(), line);
  } else {
    std::fprintf(stderr, "%s[%s %s]%s %.*s (%.*s:%d)\n",
                 color_on, TagFor(severity), ts.c_str(),
                 color_off,
                 static_cast<int>(message.size()), message.data(),
                 static_cast<int>(file.size()), file.data(), line);
  }
  std::fflush(stderr);
}

}  // namespace talos