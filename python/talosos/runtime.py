"""High-level runtime: Pythonic wrappers over the pybind11 bindings.

Usage:

    from talosos.runtime import Node, NodeOptions
    from talosos.messages import Float64

    node = Node.create("py_demo")
    pub = node.advertise("/demo/f64", Float64)
    sub = node.subscribe("/demo/f64", Float64, lambda m: print(m.data))
    pub.publish(Float64(data=3.14))
    node.spin()
"""

from typing import Any, Callable, Dict, List, Optional, Type, TypeVar

import struct
from dataclasses import is_dataclass

from . import cdr as _cdr
from . import messages as _msgs

try:
    from . import _talosos_runtime as _rt
except ImportError as ex:  # pragma: no cover
    raise ImportError(
        "talosos._talosos_runtime was not built. Rebuild TalosOS with "
        "TALOSOS_BUILD_PYTHON=ON and pybind11 available."
    ) from ex

MessageT = TypeVar("MessageT")

def init(argv=None):
    # type: (Optional[List[str]]) -> None
    _rt.init(list(argv) if argv else [])

def ok() -> bool:
    return _rt.ok()

def shutdown() -> None:
    _rt.shutdown()

class NodeOptions(_rt.NodeOptions):
    """Thin alias so user code can `from talosos.runtime import NodeOptions`."""


# ---------------------------------------------------------------------------
# 定时 / 计时工具 —— 与 C++ `talos::Rate` / `talos::Timer` / `talos::Stopwatch`
# 一一对应，方便在 while/loop 里做定频控制或做耗时测量。
# ---------------------------------------------------------------------------

import time as _time           # noqa: E402
import threading as _threading # noqa: E402
import sys as _sys             # noqa: E402


class Rate:
    """ROS1 风定频循环睡眠器。

    用法：
        rate = Rate(50)                 # 50 Hz
        while ok():
            do_work()
            rate.sleep()                # 自动 sleep 到下一个周期点

    `sleep()` 返回 `True` 表示正常休眠；`False` 表示这一轮已经超时（没
    睡）。`cycle_time` 反映上一轮实际花了多久。
    """

    __slots__ = ("_period", "_last", "_cycle")

    def __init__(self, hz: float) -> None:
        if hz <= 0:
            raise ValueError(f"Rate: hz must be > 0, got {hz}")
        self._period = 1.0 / float(hz)
        self._last = _time.monotonic()
        self._cycle = 0.0

    def sleep(self) -> bool:
        now = _time.monotonic()
        target = self._last + self._period
        if now < target:
            _time.sleep(target - now)
            self._cycle = target - self._last
            self._last = target
            return True
        self._cycle = now - self._last
        self._last = now
        return False

    def reset(self) -> None:
        self._last = _time.monotonic()

    @property
    def hz(self) -> float:       return 1.0 / self._period
    @property
    def period(self) -> float:   return self._period
    @property
    def cycle_time(self) -> float: return self._cycle


class Stopwatch:
    """秒表 —— 构造时自动开始计时，`seconds()` 等读当前已过秒数。"""

    __slots__ = ("_start",)

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._start = _time.monotonic()

    def seconds(self) -> float:
        return _time.monotonic() - self._start

    def milliseconds(self) -> float:
        return (self.seconds()) * 1000.0

    def microseconds(self) -> float:
        return (self.seconds()) * 1e6

    def __enter__(self):        # with Stopwatch() as sw: ...
        self.reset(); return self
    def __exit__(self, *a):
        return False


# MATLAB 风 tic / toc —— 每线程独立
_tic_local = _threading.local()

def tic() -> None:
    """记录当前时刻作为 tic 点。"""
    _tic_local.t = _time.monotonic()

def toc() -> float:
    """返回自最近一次 `tic()` 以来的秒数。未调用过 `tic()` 则返回 0。"""
    t = getattr(_tic_local, "t", None)
    if t is None:
        _tic_local.t = _time.monotonic()
        return 0.0
    return _time.monotonic() - t

def toc_reset() -> float:
    """`toc()` 然后顺便 `tic()`，方便连续测几段。"""
    s = toc(); tic(); return s


class Timer:
    """周期 / 一次性定时器 —— 后台线程调 callback。

    用法：
        t = Timer(0.1, lambda: print("tick"))     # 10 Hz
        one = Timer(3.0, lambda: print("later"), oneshot=True)
        t.cancel()     # 显式停止；否则 __del__ / 作用域结束时自动 cancel

    把 Timer 作为成员变量持有，即可保持回调活动；失去引用被 GC 时自动
    停止。回调里抛异常被捕获、打到 stderr，不会杀定时器线程。
    """

    def __init__(self, period_sec: float, callback, oneshot: bool = False) -> None:
        if period_sec <= 0 or not callable(callback):
            self._stop = _threading.Event(); self._stop.set()
            self._thread = None; return
        self._period = float(period_sec)
        self._cb = callback
        self._oneshot = bool(oneshot)
        self._stop = _threading.Event()
        self._thread = _threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        next_t = _time.monotonic() + self._period
        while not self._stop.is_set():
            sleep_for = next_t - _time.monotonic()
            if sleep_for > 0:
                if self._stop.wait(timeout=sleep_for):
                    return
            try:
                self._cb()
            except Exception as ex:
                print(f"talos Timer callback error: {ex}", file=_sys.stderr)
            if self._oneshot:
                return
            next_t += self._period

    def cancel(self) -> None:
        self._stop.set()
        t = getattr(self, "_thread", None)
        if t and t.is_alive() and t is not _threading.current_thread():
            t.join(timeout=1.0)

    def __del__(self):
        try: self.cancel()
        except Exception: pass

# ---------------------------------------------------------------------------
# Serialization bridge: use the same field-path / decode machinery from
# talosos.messages, and emit CDR bytes via struct for outbound messages.
# ---------------------------------------------------------------------------

def _encode(value: Any) -> bytes:
    """Encode a message dataclass instance to CDR bytes."""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    writer = _CdrWriter()
    _write_any(writer, value)
    return writer.to_bytes()

def _decode(type_cls: Type, payload: bytes) -> Any:
    if type_cls is bytes:
        return payload
    return type_cls.read(_cdr.CdrReader(payload))

# ---- Minimal CDR writer mirroring the C++ side (used only for Python-side pub) ----

class _CdrWriter:
    __slots__ = ("_buf",)

    def __init__(self) -> None:
        self._buf = bytearray(b"\x00\x01\x00\x00")

    def _align(self, n: int) -> None:
        body = len(self._buf) - 4
        pad = (n - (body % n)) % n
        self._buf.extend(b"\x00" * pad)

    def u8(self, v: int) -> None:      self._buf.append(v & 0xFF)
    def bool_(self, v: bool) -> None:  self.u8(1 if v else 0)
    def i8(self, v: int) -> None:      self.u8(v & 0xFF)

    def u16(self, v: int) -> None:
        self._align(2); self._buf.extend(struct.pack("<H", v & 0xFFFF))
    def i16(self, v: int) -> None:
        self._align(2); self._buf.extend(struct.pack("<h", v))
    def u32(self, v: int) -> None:
        self._align(4); self._buf.extend(struct.pack("<I", v & 0xFFFFFFFF))
    def i32(self, v: int) -> None:
        self._align(4); self._buf.extend(struct.pack("<i", v))
    def u64(self, v: int) -> None:
        self._align(8); self._buf.extend(struct.pack("<Q", v & 0xFFFFFFFFFFFFFFFF))
    def i64(self, v: int) -> None:
        self._align(8); self._buf.extend(struct.pack("<q", v))
    def f32(self, v: float) -> None:
        self._align(4); self._buf.extend(struct.pack("<f", v))
    def f64(self, v: float) -> None:
        self._align(8); self._buf.extend(struct.pack("<d", v))

    def string(self, s: str) -> None:
        encoded = s.encode("utf-8")
        self.u32(len(encoded) + 1)
        self._buf.extend(encoded)
        self._buf.append(0)

    def raw(self, data: bytes) -> None:
        self._buf.extend(data)

    def to_bytes(self) -> bytes:
        return bytes(self._buf)

# Map message classes to CDR writers. For scalar `data`-only messages we key by
# the TYPE_NAME declared on the class; otherwise we look up _WRITERS_BY_CLASS.

def _write_any(w: _CdrWriter, value: Any) -> None:
    cls = type(value)
    writer = _WRITERS_BY_CLASS.get(cls)
    if writer:
        writer(w, value)
        return
    # Fallback: by TYPE_NAME attribute (scalar wrappers).
    tn = getattr(cls, "TYPE_NAME", None)
    if tn and tn in _WRITERS_BY_NAME:
        _WRITERS_BY_NAME[tn](w, value)
        return
    raise TypeError(f"no CDR writer registered for {cls.__name__}")

def _w_scalar_string(w, v): w.string(v.data)
def _w_scalar_bool(w, v):   w.bool_(v.data)
def _w_scalar_i8(w, v):     w.i8(v.data)
def _w_scalar_i16(w, v):    w.i16(v.data)
def _w_scalar_i32(w, v):    w.i32(v.data)
def _w_scalar_i64(w, v):    w.i64(v.data)
def _w_scalar_u8(w, v):     w.u8(v.data)
def _w_scalar_u16(w, v):    w.u16(v.data)
def _w_scalar_u32(w, v):    w.u32(v.data)
def _w_scalar_u64(w, v):    w.u64(v.data)
def _w_scalar_f32(w, v):    w.f32(v.data)
def _w_scalar_f64(w, v):    w.f64(v.data)

_WRITERS_BY_NAME = {  # type: Dict[str, Callable[[_CdrWriter, Any], None]]
    "String":  _w_scalar_string,
    "Bool":    _w_scalar_bool,
    "Int8":    _w_scalar_i8,  "Int16": _w_scalar_i16,
    "Int32":   _w_scalar_i32, "Int64": _w_scalar_i64,
    "UInt8":   _w_scalar_u8,  "UInt16": _w_scalar_u16,
    "UInt32":  _w_scalar_u32, "UInt64": _w_scalar_u64,
    "Float32": _w_scalar_f32, "Float64": _w_scalar_f64,
}

# Header + a few composites for completeness (publishing from Python supports
# std_msgs scalars and Header-bearing messages below).

def _w_time(w, v):
    w.i32(v.sec); w.u32(v.nanosec)

def _w_header(w, v):
    _w_time(w, v.stamp); w.string(v.frame_id)

def _w_vec3(w, v):
    w.f64(v.x); w.f64(v.y); w.f64(v.z)

def _w_quat(w, v):
    w.f64(v.x); w.f64(v.y); w.f64(v.z); w.f64(v.w)

def _w_pose(w, v):
    _w_vec3(w, v.position); _w_quat(w, v.orientation)

def _w_pose_stamped(w, v):
    _w_header(w, v.header); _w_pose(w, v.pose)

def _w_twist(w, v):
    _w_vec3(w, v.linear); _w_vec3(w, v.angular)

def _w_twist_stamped(w, v):
    _w_header(w, v.header); _w_twist(w, v.twist)

def _w_compressed_image(w, v):
    _w_header(w, v.header)
    w.string(v.format)
    data = bytes(v.data)
    w.u32(len(data))
    w.raw(data)

def _w_laser_scan(w, v):
    _w_header(w, v.header)
    w.f32(v.angle_min); w.f32(v.angle_max)
    w.f32(v.angle_increment)
    w.f32(v.time_increment); w.f32(v.scan_time)
    w.f32(v.range_min); w.f32(v.range_max)
    w.u32(len(v.ranges))
    for r in v.ranges: w.f32(r)
    w.u32(len(v.intensities))
    for i in v.intensities: w.f32(i)

def _w_point_field(w, v):
    w.string(v.name)
    w.u32(v.offset)
    w.u8(v.datatype)
    w.u32(v.count)

def _w_point_cloud2(w, v):
    _w_header(w, v.header)
    w.u32(v.height); w.u32(v.width)
    w.u32(len(v.fields))
    for f in v.fields: _w_point_field(w, f)
    w.bool_(v.is_bigendian)
    w.u32(v.point_step); w.u32(v.row_step)
    data = bytes(v.data)
    w.u32(len(data))
    w.raw(data)
    w.bool_(v.is_dense)

def _w_map_metadata(w, v):
    _w_time(w, v.map_load_time)
    w.f32(v.resolution)
    w.u32(v.width); w.u32(v.height)
    _w_pose(w, v.origin)

def _w_occupancy_grid(w, v):
    _w_header(w, v.header)
    _w_map_metadata(w, v.info)
    data = v.data if isinstance(v.data, (bytes, bytearray)) else bytes(v.data)
    w.u32(len(data)); w.raw(bytes(data))

def _w_octomap(w, v):
    _w_header(w, v.header)
    w.bool_(v.binary)
    w.string(v.id)
    w.f64(v.resolution)
    data = v.data if isinstance(v.data, (bytes, bytearray)) else bytes(v.data)
    w.u32(len(data)); w.raw(bytes(data))

def _w_octomap_with_pose(w, v):
    _w_header(w, v.header)
    _w_pose(w, v.origin)
    _w_octomap(w, v.octomap)

def _w_image(w, v):
    _w_header(w, v.header)
    w.u32(v.height); w.u32(v.width)
    w.string(v.encoding)
    w.u8(int(v.is_bigendian) & 0xFF)
    w.u32(v.step)
    data = v.data if isinstance(v.data, (bytes, bytearray)) else bytes(v.data)
    w.u32(len(data)); w.raw(bytes(data))

def _w_imu(w, v):
    _w_header(w, v.header)
    _w_quat(w, v.orientation)
    for x in v.orientation_covariance:         w.f64(float(x))
    _w_vec3(w, v.angular_velocity)
    for x in v.angular_velocity_covariance:    w.f64(float(x))
    _w_vec3(w, v.linear_acceleration)
    for x in v.linear_acceleration_covariance: w.f64(float(x))

def _w_duration(w, v):
    # Duration 线上与 Time 同形：i32 sec + u32 nanosec
    w.i32(int(v.sec)); w.u32(int(v.nanosec))

def _w_transform(w, v):
    _w_vec3(w, v.translation); _w_quat(w, v.rotation)

def _w_transform_stamped(w, v):
    _w_header(w, v.header)
    w.string(v.child_frame_id)
    _w_transform(w, v.transform)

def _w_tf_message(w, v):
    w.u32(len(v.transforms))
    for t in v.transforms:
        _w_transform_stamped(w, t)

def _w_color_rgba(w, v):
    w.f32(float(v.r)); w.f32(float(v.g)); w.f32(float(v.b)); w.f32(float(v.a))

def _w_point(w, v):
    w.f64(float(v.x)); w.f64(float(v.y)); w.f64(float(v.z))

def _w_marker(w, v):
    _w_header(w, v.header)
    w.string(v.ns); w.i32(int(v.id)); w.i32(int(v.type)); w.i32(int(v.action))
    _w_pose(w, v.pose)
    _w_vec3(w, v.scale)
    _w_color_rgba(w, v.color)
    _w_duration(w, v.lifetime)
    w.bool_(bool(v.frame_locked))
    w.u32(len(v.points))
    for p in v.points: _w_point(w, p)
    w.u32(len(v.colors))
    for c in v.colors: _w_color_rgba(w, c)
    w.string(v.text); w.string(v.mesh_resource)
    w.bool_(bool(v.mesh_use_embedded_materials))

def _w_marker_array(w, v):
    w.u32(len(v.markers))
    for m in v.markers: _w_marker(w, m)

_WRITERS_BY_CLASS = {  # type: Dict[type, Callable[[_CdrWriter, Any], None]]
    _msgs.PoseStamped:     _w_pose_stamped,
    _msgs.TwistStamped:    _w_twist_stamped,
    _msgs.CompressedImage: _w_compressed_image,
    _msgs.Image:           _w_image,
    _msgs.Imu:             _w_imu,
    _msgs.LaserScan:       _w_laser_scan,
    _msgs.PointCloud2:     _w_point_cloud2,
    _msgs.OccupancyGrid:   _w_occupancy_grid,
    _msgs.Octomap:         _w_octomap,
    _msgs.OctomapWithPose: _w_octomap_with_pose,
    _msgs.TransformStamped: _w_transform_stamped,
    _msgs.TFMessage:       _w_tf_message,
    _msgs.Marker:          _w_marker,
    _msgs.MarkerArray:     _w_marker_array,
}

# ---------------------------------------------------------------------------
# Pythonic wrappers for Publisher/Subscription/Service
# ---------------------------------------------------------------------------

class Publisher:
    __slots__ = ("_raw", "_type")

    def __init__(self, raw, type_cls: Type) -> None:
        self._raw = raw
        self._type = type_cls

    def publish(self, message: Any) -> None:
        self._raw.publish(_encode(message))

    @property
    def key(self) -> str:
        return self._raw.key

class Subscription:
    __slots__ = ("_raw", "_type")

    def __init__(self, raw, type_cls: Type) -> None:
        self._raw = raw
        self._type = type_cls

    @property
    def key(self) -> str:
        return self._raw.key

class ServiceClient:
    __slots__ = ("_raw", "_req_cls", "_resp_cls")

    def __init__(self, raw, req_cls: Type, resp_cls: Type) -> None:
        self._raw = raw
        self._req_cls = req_cls
        self._resp_cls = resp_cls

    def call(self, request: Any, timeout_ms: int = 3000) -> Optional[Any]:
        payload = _encode(request) if not isinstance(request, (bytes, bytearray))\
            else bytes(request)
        resp = self._raw.call(payload, timeout_ms)
        if resp is None:
            return None
        return _decode(self._resp_cls, resp)

class Service:
    __slots__ = ("_raw",)

    def __init__(self, raw) -> None:
        self._raw = raw

class Node:
    def __init__(self, raw_node) -> None:
        self._raw = raw_node
        # Hold onto subscription/service objects so callers don't have to —
        # dropping the Python handle is easy to miss and kills delivery.
        self._subscriptions = []  # type: List[Subscription]
        self._services = []       # type: List[Service]

    @classmethod
    def create(cls, name, options=None, *, ns="", mode="",
                connect=None, listen=None, multicast=True):
        # type: (str, Optional[NodeOptions], str, str, Optional[List[str]], Optional[List[str]], bool) -> "Node"
        opts = options or NodeOptions()
        if ns:       opts.ns = ns
        if mode:     opts.mode = mode
        if connect:  opts.connect = list(connect)
        if listen:   opts.listen = list(listen)
        opts.multicast = multicast
        return cls(_rt.Node.create(name, opts))

    @property
    def name(self) -> str:
        return self._raw.name

    @property
    def ns(self) -> str:
        return self._raw.ns

    @property
    def fully_qualified_name(self) -> str:
        return self._raw.fully_qualified_name

    def resolve_topic(self, topic: str) -> str:
        return self._raw.resolve_topic(topic)

    def advertise(self, topic: str, type_cls: Type) -> Publisher:
        return Publisher(self._raw.advertise(topic), type_cls)

    def subscribe(self, topic: str, type_cls: Type,
                    callback: Callable[[Any], None]) -> Subscription:
        def on_bytes(payload: bytes) -> None:
            try:
                msg = _decode(type_cls, payload)
            except Exception as ex:
                import sys
                print(f"subscription decode error on {topic}: {ex}",
                        file=sys.stderr)
                return
            callback(msg)
        sub = Subscription(self._raw.subscribe(topic, on_bytes), type_cls)
        self._subscriptions.append(sub)
        return sub

    def advertise_service(self, name: str,
                            request_cls: Type, response_cls: Type,
                            handler: Callable[[Any], Any]) -> Service:
        def on_request(payload: bytes) -> bytes:
            try:
                req = _decode(request_cls, payload)
                resp = handler(req)
                if resp is None:
                    return b""
                return _encode(resp)
            except Exception as ex:
                import sys
                print(f"service handler error: {ex}", file=sys.stderr)
                return b""
        svc = Service(self._raw.advertise_service(name, on_request))
        self._services.append(svc)
        return svc

    def create_service_client(self, name: str,
                                 request_cls: Type,
                                 response_cls: Type) -> ServiceClient:
        raw = self._raw.create_service_client(name)
        return ServiceClient(raw, request_cls, response_cls)

    def spin(self) -> None:
        self._raw.spin()

__all__ = [
    "Node", "NodeOptions", "Publisher", "Subscription", "Service",
    "ServiceClient", "init", "ok", "shutdown",
]
