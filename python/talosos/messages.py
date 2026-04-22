"""Python mirrors of a useful subset of TalosOS messages for plot/viz.

Only readers are provided here — publication from Python lands when the
pybind11 runtime bindings arrive in a later phase.
"""

from typing import Callable, ClassVar

from dataclasses import dataclass, field

from .cdr import CdrReader

# ---------------------------------------------------------------------------
# Primitives shared by many messages
# ---------------------------------------------------------------------------

@dataclass
class Time:
    sec: int = 0
    nanosec: int = 0

    @staticmethod
    def read(r: CdrReader) -> "Time":
        return Time(sec=r.i32(), nanosec=r.u32())

    def seconds(self) -> float:
        return self.sec + self.nanosec * 1e-9

@dataclass
class Duration:
    sec: int = 0
    nanosec: int = 0

    @staticmethod
    def read(r: CdrReader) -> "Duration":
        return Duration(sec=r.i32(), nanosec=r.i32())

@dataclass
class Header:
    stamp: Time = field(default_factory=Time)
    frame_id: str = ""

    @staticmethod
    def read(r: CdrReader) -> "Header":
        return Header(stamp=Time.read(r), frame_id=r.string())

# ---------------------------------------------------------------------------
# std_msgs
# ---------------------------------------------------------------------------

def _wrap_scalar(name: str, reader_fn: Callable[[CdrReader], object]):
    @dataclass
    class _Msg:
        data: object = None
        TYPE_NAME: ClassVar[str] = name

        @classmethod
        def read(cls, r: CdrReader):
            return cls(data=reader_fn(r))
    _Msg.__name__ = name
    _Msg.__qualname__ = name
    return _Msg

String  = _wrap_scalar("String",  lambda r: r.string())
Bool    = _wrap_scalar("Bool",    lambda r: r.bool_())
Int8    = _wrap_scalar("Int8",    lambda r: r.i8())
Int16   = _wrap_scalar("Int16",   lambda r: r.i16())
Int32   = _wrap_scalar("Int32",   lambda r: r.i32())
Int64   = _wrap_scalar("Int64",   lambda r: r.i64())
UInt8   = _wrap_scalar("UInt8",   lambda r: r.u8())
UInt16  = _wrap_scalar("UInt16",  lambda r: r.u16())
UInt32  = _wrap_scalar("UInt32",  lambda r: r.u32())
UInt64  = _wrap_scalar("UInt64",  lambda r: r.u64())
Float32 = _wrap_scalar("Float32", lambda r: r.f32())
Float64 = _wrap_scalar("Float64", lambda r: r.f64())

@dataclass
class ColorRGBA:
    r: float = 0.0
    g: float = 0.0
    b: float = 0.0
    a: float = 1.0

    @staticmethod
    def read(reader: CdrReader) -> "ColorRGBA":
        return ColorRGBA(r=reader.f32(), g=reader.f32(), b=reader.f32(), a=reader.f32())

# ---------------------------------------------------------------------------
# geometry_msgs
# ---------------------------------------------------------------------------

@dataclass
class Vector3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    @staticmethod
    def read(r: CdrReader) -> "Vector3":
        return Vector3(x=r.f64(), y=r.f64(), z=r.f64())

@dataclass
class Point:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    @staticmethod
    def read(r: CdrReader) -> "Point":
        return Point(x=r.f64(), y=r.f64(), z=r.f64())

@dataclass
class Quaternion:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    w: float = 1.0

    @staticmethod
    def read(r: CdrReader) -> "Quaternion":
        return Quaternion(x=r.f64(), y=r.f64(), z=r.f64(), w=r.f64())

@dataclass
class Pose:
    position: Point = field(default_factory=Point)
    orientation: Quaternion = field(default_factory=Quaternion)

    @staticmethod
    def read(r: CdrReader) -> "Pose":
        return Pose(position=Point.read(r), orientation=Quaternion.read(r))

@dataclass
class PoseStamped:
    header: Header = field(default_factory=Header)
    pose: Pose = field(default_factory=Pose)
    TYPE_NAME: ClassVar[str] = "PoseStamped"

    @classmethod
    def read(cls, r: CdrReader) -> "PoseStamped":
        return cls(header=Header.read(r), pose=Pose.read(r))

@dataclass
class Twist:
    linear: Vector3 = field(default_factory=Vector3)
    angular: Vector3 = field(default_factory=Vector3)

    @staticmethod
    def read(r: CdrReader) -> "Twist":
        return Twist(linear=Vector3.read(r), angular=Vector3.read(r))

@dataclass
class TwistStamped:
    header: Header = field(default_factory=Header)
    twist: Twist = field(default_factory=Twist)
    TYPE_NAME: ClassVar[str] = "TwistStamped"

    @classmethod
    def read(cls, r: CdrReader) -> "TwistStamped":
        return cls(header=Header.read(r), twist=Twist.read(r))

@dataclass
class Transform:
    translation: Vector3 = field(default_factory=Vector3)
    rotation: Quaternion = field(default_factory=Quaternion)

    @staticmethod
    def read(r: CdrReader) -> "Transform":
        return Transform(translation=Vector3.read(r), rotation=Quaternion.read(r))

@dataclass
class TransformStamped:
    header: Header = field(default_factory=Header)
    child_frame_id: str = ""
    transform: Transform = field(default_factory=Transform)
    TYPE_NAME: ClassVar[str] = "TransformStamped"

    @classmethod
    def read(cls, r: CdrReader) -> "TransformStamped":
        return cls(
            header=Header.read(r),
            child_frame_id=r.string(),
            transform=Transform.read(r),
        )

# ---------------------------------------------------------------------------
# sensor_msgs
# ---------------------------------------------------------------------------

@dataclass
class Imu:
    header: Header = field(default_factory=Header)
    orientation: Quaternion = field(default_factory=Quaternion)
    orientation_covariance: list = field(default_factory=lambda: [0.0] * 9)
    angular_velocity: Vector3 = field(default_factory=Vector3)
    angular_velocity_covariance: list = field(default_factory=lambda: [0.0] * 9)
    linear_acceleration: Vector3 = field(default_factory=Vector3)
    linear_acceleration_covariance: list = field(default_factory=lambda: [0.0] * 9)
    TYPE_NAME: ClassVar[str] = "Imu"

    @classmethod
    def read(cls, r: CdrReader) -> "Imu":
        header = Header.read(r)
        orient = Quaternion.read(r)
        oc = [r.f64() for _ in range(9)]
        av = Vector3.read(r)
        avc = [r.f64() for _ in range(9)]
        la = Vector3.read(r)
        lac = [r.f64() for _ in range(9)]
        return cls(header=header, orientation=orient,
                     orientation_covariance=oc,
                     angular_velocity=av,
                     angular_velocity_covariance=avc,
                     linear_acceleration=la,
                     linear_acceleration_covariance=lac)

@dataclass
class Image:
    header: Header = field(default_factory=Header)
    height: int = 0
    width: int = 0
    encoding: str = ""
    is_bigendian: int = 0
    step: int = 0
    data: bytes = b""
    TYPE_NAME: ClassVar[str] = "Image"

    @classmethod
    def read(cls, r: CdrReader) -> "Image":
        header = Header.read(r)
        h = r.u32()
        w = r.u32()
        enc = r.string()
        big = r.u8()
        step = r.u32()
        data = r.sequence_u8()
        return cls(header=header, height=h, width=w, encoding=enc,
                     is_bigendian=big, step=step, data=data)

@dataclass
class CompressedImage:
    header: Header = field(default_factory=Header)
    format: str = ""
    data: bytes = b""
    TYPE_NAME: ClassVar[str] = "CompressedImage"

    @classmethod
    def read(cls, r: CdrReader) -> "CompressedImage":
        header = Header.read(r)
        fmt = r.string()
        data = r.sequence_u8()
        return cls(header=header, format=fmt, data=data)

@dataclass
class LaserScan:
    header: Header = field(default_factory=Header)
    angle_min: float = 0.0
    angle_max: float = 0.0
    angle_increment: float = 0.0
    time_increment: float = 0.0
    scan_time: float = 0.0
    range_min: float = 0.0
    range_max: float = 0.0
    ranges: list = field(default_factory=list)
    intensities: list = field(default_factory=list)
    TYPE_NAME: ClassVar[str] = "LaserScan"

    @classmethod
    def read(cls, r: CdrReader) -> "LaserScan":
        header = Header.read(r)
        amin = r.f32(); amax = r.f32()
        inc = r.f32()
        tinc = r.f32(); stime = r.f32()
        rmin = r.f32(); rmax = r.f32()
        ranges = r.sequence(lambda rr: rr.f32())
        intens = r.sequence(lambda rr: rr.f32())
        return cls(header=header, angle_min=amin, angle_max=amax,
                     angle_increment=inc, time_increment=tinc,
                     scan_time=stime, range_min=rmin, range_max=rmax,
                     ranges=ranges, intensities=intens)

@dataclass
class PointField:
    INT8    : ClassVar[int] = 1
    UINT8   : ClassVar[int] = 2
    INT16   : ClassVar[int] = 3
    UINT16  : ClassVar[int] = 4
    INT32   : ClassVar[int] = 5
    UINT32  : ClassVar[int] = 6
    FLOAT32 : ClassVar[int] = 7
    FLOAT64 : ClassVar[int] = 8

    name: str = ""
    offset: int = 0
    datatype: int = 0
    count: int = 0

    @staticmethod
    def read(r: CdrReader) -> "PointField":
        return PointField(name=r.string(), offset=r.u32(),
                           datatype=r.u8(), count=r.u32())

@dataclass
class PointCloud2:
    header: Header = field(default_factory=Header)
    height: int = 0
    width: int = 0
    fields: list = field(default_factory=list)
    is_bigendian: bool = False
    point_step: int = 0
    row_step: int = 0
    data: bytes = b""
    is_dense: bool = False
    TYPE_NAME: ClassVar[str] = "PointCloud2"

    @classmethod
    def read(cls, r: CdrReader) -> "PointCloud2":
        header = Header.read(r)
        h = r.u32(); w = r.u32()
        fields = r.sequence(lambda rr: PointField.read(rr))
        be = r.bool_()
        ps = r.u32(); rs = r.u32()
        data = r.sequence_u8()
        dense = r.bool_()
        return cls(header=header, height=h, width=w, fields=fields,
                     is_bigendian=be, point_step=ps, row_step=rs,
                     data=data, is_dense=dense)

# ---------------------------------------------------------------------------
# visualization_msgs
# ---------------------------------------------------------------------------

@dataclass
class Marker:
    ARROW: ClassVar[int] = 0
    CUBE: ClassVar[int] = 1
    SPHERE: ClassVar[int] = 2
    CYLINDER: ClassVar[int] = 3
    LINE_STRIP: ClassVar[int] = 4
    LINE_LIST: ClassVar[int] = 5
    CUBE_LIST: ClassVar[int] = 6
    SPHERE_LIST: ClassVar[int] = 7
    POINTS: ClassVar[int] = 8
    TEXT_VIEW_FACING: ClassVar[int] = 9
    MESH_RESOURCE: ClassVar[int] = 10
    TRIANGLE_LIST: ClassVar[int] = 11

    header: Header = field(default_factory=Header)
    ns: str = ""
    id: int = 0
    type: int = 0
    action: int = 0
    pose: Pose = field(default_factory=Pose)
    scale: Vector3 = field(default_factory=Vector3)
    color: ColorRGBA = field(default_factory=ColorRGBA)
    lifetime: Duration = field(default_factory=Duration)
    frame_locked: bool = False
    points: list = field(default_factory=list)
    colors: list = field(default_factory=list)
    text: str = ""
    mesh_resource: str = ""
    mesh_use_embedded_materials: bool = False
    TYPE_NAME: ClassVar[str] = "Marker"

    @classmethod
    def read(cls, r: CdrReader) -> "Marker":
        header = Header.read(r)
        ns = r.string(); mid = r.i32()
        mt = r.i32(); act = r.i32()
        pose = Pose.read(r); scale = Vector3.read(r); color = ColorRGBA.read(r)
        lifetime = Duration.read(r)
        fl = r.bool_()
        points = r.sequence(lambda rr: Point.read(rr))
        colors = r.sequence(lambda rr: ColorRGBA.read(rr))
        text = r.string(); mesh = r.string()
        emb = r.bool_()
        return cls(header=header, ns=ns, id=mid, type=mt, action=act,
                     pose=pose, scale=scale, color=color, lifetime=lifetime,
                     frame_locked=fl, points=points, colors=colors,
                     text=text, mesh_resource=mesh,
                     mesh_use_embedded_materials=emb)

@dataclass
class MarkerArray:
    markers: list = field(default_factory=list)
    TYPE_NAME: ClassVar[str] = "MarkerArray"

    @classmethod
    def read(cls, r: CdrReader) -> "MarkerArray":
        return cls(markers=r.sequence(lambda rr: Marker.read(rr)))

# ---------------------------------------------------------------------------
# nav_msgs / octomap_msgs
# ---------------------------------------------------------------------------

@dataclass
class MapMetaData:
    map_load_time: Time = field(default_factory=Time)
    resolution: float = 0.0
    width: int = 0
    height: int = 0
    origin: Pose = field(default_factory=Pose)
    TYPE_NAME: ClassVar[str] = "MapMetaData"

    @classmethod
    def read(cls, r: CdrReader) -> "MapMetaData":
        t = Time.read(r); res = r.f32()
        w = r.u32(); h = r.u32()
        origin = Pose.read(r)
        return cls(map_load_time=t, resolution=res, width=w, height=h,
                     origin=origin)


@dataclass
class OccupancyGrid:
    header: Header = field(default_factory=Header)
    info: MapMetaData = field(default_factory=MapMetaData)
    # -1 = unknown, 0 = free, 1..100 = occupancy 概率 (%)；wire 上是 int8
    data: bytes = b""
    TYPE_NAME: ClassVar[str] = "OccupancyGrid"

    @classmethod
    def read(cls, r: CdrReader) -> "OccupancyGrid":
        hdr = Header.read(r); info = MapMetaData.read(r)
        data = r.sequence_u8()   # int8 与 uint8 在线上同样是 1 字节
        return cls(header=hdr, info=info, data=data)


@dataclass
class Octomap:
    header: Header = field(default_factory=Header)
    binary: bool = False
    id: str = ""
    resolution: float = 0.0
    data: bytes = b""   # octomap binary tree payload；格式由 `id` 决定
    TYPE_NAME: ClassVar[str] = "Octomap"

    @classmethod
    def read(cls, r: CdrReader) -> "Octomap":
        hdr = Header.read(r)
        binary = r.bool_()
        mid = r.string()
        res = r.f64()
        data = r.sequence_u8()
        return cls(header=hdr, binary=binary, id=mid, resolution=res, data=data)


@dataclass
class OctomapWithPose:
    header: Header = field(default_factory=Header)
    origin: Pose = field(default_factory=Pose)
    octomap: Octomap = field(default_factory=Octomap)
    TYPE_NAME: ClassVar[str] = "OctomapWithPose"

    @classmethod
    def read(cls, r: CdrReader) -> "OctomapWithPose":
        hdr = Header.read(r)
        origin = Pose.read(r)
        oc = Octomap.read(r)
        return cls(header=hdr, origin=origin, octomap=oc)


# ---------------------------------------------------------------------------
# tf2_msgs
# ---------------------------------------------------------------------------

@dataclass
class TFMessage:
    transforms: list = field(default_factory=list)
    TYPE_NAME: ClassVar[str] = "TFMessage"

    @classmethod
    def read(cls, r: CdrReader) -> "TFMessage":
        return cls(transforms=r.sequence(lambda rr: TransformStamped.read(rr)))

# ---------------------------------------------------------------------------
# Type registry
# ---------------------------------------------------------------------------

REGISTRY = {
    "String":  String,
    "Bool":    Bool,
    "Int8":    Int8,  "Int16":   Int16,
    "Int32":   Int32, "Int64":   Int64,
    "UInt8":   UInt8, "UInt16":  UInt16,
    "UInt32":  UInt32, "UInt64": UInt64,
    "Float32": Float32, "Float64": Float64,
    "PoseStamped": PoseStamped,
    "TwistStamped": TwistStamped,
    "TransformStamped": TransformStamped,
    "Imu": Imu,
    "Image": Image,
    "CompressedImage": CompressedImage,
    "LaserScan": LaserScan,
    "PointCloud2": PointCloud2,
    "Marker": Marker,
    "MarkerArray": MarkerArray,
    "TFMessage": TFMessage,
    "OccupancyGrid":    OccupancyGrid,
    "MapMetaData":      MapMetaData,
    "Octomap":          Octomap,
    "OctomapWithPose":  OctomapWithPose,
}

def resolve_type(name: str):
    try:
        return REGISTRY[name]
    except KeyError as e:
        raise KeyError(
            f"unknown message type {name!r}. Supported: "
            f"{', '.join(sorted(REGISTRY))}"
        ) from e

def decode(type_name: str, payload: bytes):
    return resolve_type(type_name).read(CdrReader(payload))

def field_path(obj, path: str):
    """Resolve a dotted field path on a decoded message."""
    cur = obj
    for part in path.split("."):
        if part == "":
            continue
        if hasattr(cur, part):
            cur = getattr(cur, part)
        else:
            raise AttributeError(
                f"field path {path!r}: no attribute {part!r} on "
                f"{type(cur).__name__}")
    return cur
