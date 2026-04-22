#ifndef TALOSOS_MSGS_SENSOR_MSGS_H_
#define TALOSOS_MSGS_SENSOR_MSGS_H_

#include <array>
#include <cstdint>
#include <string>
#include <vector>

#include "talosos/msgs/geometry_msgs.h"
#include "talosos/msgs/std_msgs.h"
#include "talosos/serialization.h"
#include "talosos/time.h"

namespace talos::msgs {

// ---- RegionOfInterest (used by CameraInfo) ----

struct RegionOfInterest {
  uint32_t x_offset = 0;
  uint32_t y_offset = 0;
  uint32_t height = 0;
  uint32_t width = 0;
  bool do_rectify = false;
};
inline void Write(cdr::Writer& w, const RegionOfInterest& m) {
  cdr::Write(w, m.x_offset); cdr::Write(w, m.y_offset);
  cdr::Write(w, m.height);   cdr::Write(w, m.width);
  cdr::Write(w, m.do_rectify);
}
inline void Read(cdr::Reader& r, RegionOfInterest& m) {
  cdr::Read(r, m.x_offset); cdr::Read(r, m.y_offset);
  cdr::Read(r, m.height);   cdr::Read(r, m.width);
  cdr::Read(r, m.do_rectify);
}

// ---- Imu ----

struct Imu {
  Header header;
  Quaternion orientation;
  std::array<double, 9> orientation_covariance{};
  Vector3 angular_velocity;
  std::array<double, 9> angular_velocity_covariance{};
  Vector3 linear_acceleration;
  std::array<double, 9> linear_acceleration_covariance{};
};
inline void Write(cdr::Writer& w, const Imu& m) {
  Write(w, m.header);
  Write(w, m.orientation); Write(w, m.orientation_covariance);
  Write(w, m.angular_velocity); Write(w, m.angular_velocity_covariance);
  Write(w, m.linear_acceleration); Write(w, m.linear_acceleration_covariance);
}
inline void Read(cdr::Reader& r, Imu& m) {
  Read(r, m.header);
  Read(r, m.orientation); Read(r, m.orientation_covariance);
  Read(r, m.angular_velocity); Read(r, m.angular_velocity_covariance);
  Read(r, m.linear_acceleration); Read(r, m.linear_acceleration_covariance);
}

// ---- Image / CompressedImage ----

struct Image {
  Header header;
  uint32_t height = 0;
  uint32_t width = 0;
  std::string encoding;
  uint8_t is_bigendian = 0;
  uint32_t step = 0;
  std::vector<uint8_t> data;
};
inline void Write(cdr::Writer& w, const Image& m) {
  Write(w, m.header);
  cdr::Write(w, m.height); cdr::Write(w, m.width);
  cdr::Write(w, m.encoding);
  cdr::Write(w, m.is_bigendian);
  cdr::Write(w, m.step);
  Write(w, m.data);
}
inline void Read(cdr::Reader& r, Image& m) {
  Read(r, m.header);
  cdr::Read(r, m.height); cdr::Read(r, m.width);
  cdr::Read(r, m.encoding);
  cdr::Read(r, m.is_bigendian);
  cdr::Read(r, m.step);
  Read(r, m.data);
}

struct CompressedImage {
  Header header;
  std::string format;
  std::vector<uint8_t> data;
};
inline void Write(cdr::Writer& w, const CompressedImage& m) {
  Write(w, m.header);
  cdr::Write(w, m.format);
  Write(w, m.data);
}
inline void Read(cdr::Reader& r, CompressedImage& m) {
  Read(r, m.header);
  cdr::Read(r, m.format);
  Read(r, m.data);
}

// ---- CameraInfo ----

struct CameraInfo {
  Header header;
  uint32_t height = 0;
  uint32_t width = 0;
  std::string distortion_model;
  std::vector<double> D;
  std::array<double, 9>  K{};
  std::array<double, 9>  R{};
  std::array<double, 12> P{};
  uint32_t binning_x = 0;
  uint32_t binning_y = 0;
  RegionOfInterest roi;
};
inline void Write(cdr::Writer& w, const CameraInfo& m) {
  Write(w, m.header);
  cdr::Write(w, m.height); cdr::Write(w, m.width);
  cdr::Write(w, m.distortion_model);
  Write(w, m.D);
  Write(w, m.K); Write(w, m.R); Write(w, m.P);
  cdr::Write(w, m.binning_x); cdr::Write(w, m.binning_y);
  Write(w, m.roi);
}
inline void Read(cdr::Reader& r, CameraInfo& m) {
  Read(r, m.header);
  cdr::Read(r, m.height); cdr::Read(r, m.width);
  cdr::Read(r, m.distortion_model);
  Read(r, m.D);
  Read(r, m.K); Read(r, m.R); Read(r, m.P);
  cdr::Read(r, m.binning_x); cdr::Read(r, m.binning_y);
  Read(r, m.roi);
}

// ---- LaserScan ----

struct LaserScan {
  Header header;
  float angle_min = 0.f;
  float angle_max = 0.f;
  float angle_increment = 0.f;
  float time_increment = 0.f;
  float scan_time = 0.f;
  float range_min = 0.f;
  float range_max = 0.f;
  std::vector<float> ranges;
  std::vector<float> intensities;
};
inline void Write(cdr::Writer& w, const LaserScan& m) {
  Write(w, m.header);
  cdr::Write(w, m.angle_min); cdr::Write(w, m.angle_max);
  cdr::Write(w, m.angle_increment);
  cdr::Write(w, m.time_increment); cdr::Write(w, m.scan_time);
  cdr::Write(w, m.range_min); cdr::Write(w, m.range_max);
  Write(w, m.ranges); Write(w, m.intensities);
}
inline void Read(cdr::Reader& r, LaserScan& m) {
  Read(r, m.header);
  cdr::Read(r, m.angle_min); cdr::Read(r, m.angle_max);
  cdr::Read(r, m.angle_increment);
  cdr::Read(r, m.time_increment); cdr::Read(r, m.scan_time);
  cdr::Read(r, m.range_min); cdr::Read(r, m.range_max);
  Read(r, m.ranges); Read(r, m.intensities);
}

// ---- PointCloud2 ----

struct PointField {
  static constexpr uint8_t INT8    = 1;
  static constexpr uint8_t UINT8   = 2;
  static constexpr uint8_t INT16   = 3;
  static constexpr uint8_t UINT16  = 4;
  static constexpr uint8_t INT32   = 5;
  static constexpr uint8_t UINT32  = 6;
  static constexpr uint8_t FLOAT32 = 7;
  static constexpr uint8_t FLOAT64 = 8;

  std::string name;
  uint32_t offset = 0;
  uint8_t datatype = 0;
  uint32_t count = 0;
};
inline void Write(cdr::Writer& w, const PointField& m) {
  cdr::Write(w, m.name);
  cdr::Write(w, m.offset);
  cdr::Write(w, m.datatype);
  cdr::Write(w, m.count);
}
inline void Read(cdr::Reader& r, PointField& m) {
  cdr::Read(r, m.name);
  cdr::Read(r, m.offset);
  cdr::Read(r, m.datatype);
  cdr::Read(r, m.count);
}

struct PointCloud2 {
  Header header;
  uint32_t height = 0;
  uint32_t width = 0;
  std::vector<PointField> fields;
  bool is_bigendian = false;
  uint32_t point_step = 0;
  uint32_t row_step = 0;
  std::vector<uint8_t> data;
  bool is_dense = false;
};
inline void Write(cdr::Writer& w, const PointCloud2& m) {
  Write(w, m.header);
  cdr::Write(w, m.height); cdr::Write(w, m.width);
  Write(w, m.fields);
  cdr::Write(w, m.is_bigendian);
  cdr::Write(w, m.point_step); cdr::Write(w, m.row_step);
  Write(w, m.data);
  cdr::Write(w, m.is_dense);
}
inline void Read(cdr::Reader& r, PointCloud2& m) {
  Read(r, m.header);
  cdr::Read(r, m.height); cdr::Read(r, m.width);
  Read(r, m.fields);
  cdr::Read(r, m.is_bigendian);
  cdr::Read(r, m.point_step); cdr::Read(r, m.row_step);
  Read(r, m.data);
  cdr::Read(r, m.is_dense);
}

// ---- JointState ----

struct JointState {
  Header header;
  std::vector<std::string> name;
  std::vector<double> position;
  std::vector<double> velocity;
  std::vector<double> effort;
};
inline void Write(cdr::Writer& w, const JointState& m) {
  Write(w, m.header);
  Write(w, m.name);
  Write(w, m.position);
  Write(w, m.velocity);
  Write(w, m.effort);
}
inline void Read(cdr::Reader& r, JointState& m) {
  Read(r, m.header);
  Read(r, m.name);
  Read(r, m.position);
  Read(r, m.velocity);
  Read(r, m.effort);
}

// ---- NavSat ----

struct NavSatStatus {
  static constexpr int8_t STATUS_NO_FIX   = -1;
  static constexpr int8_t STATUS_FIX      = 0;
  static constexpr int8_t STATUS_SBAS_FIX = 1;
  static constexpr int8_t STATUS_GBAS_FIX = 2;
  static constexpr uint16_t SERVICE_GPS     = 1;
  static constexpr uint16_t SERVICE_GLONASS = 2;
  static constexpr uint16_t SERVICE_COMPASS = 4;
  static constexpr uint16_t SERVICE_GALILEO = 8;

  int8_t status = STATUS_NO_FIX;
  uint16_t service = 0;
};
inline void Write(cdr::Writer& w, const NavSatStatus& m) {
  cdr::Write(w, m.status); cdr::Write(w, m.service);
}
inline void Read(cdr::Reader& r, NavSatStatus& m) {
  cdr::Read(r, m.status); cdr::Read(r, m.service);
}

struct NavSatFix {
  static constexpr uint8_t COVARIANCE_TYPE_UNKNOWN      = 0;
  static constexpr uint8_t COVARIANCE_TYPE_APPROXIMATED = 1;
  static constexpr uint8_t COVARIANCE_TYPE_DIAGONAL_KNOWN = 2;
  static constexpr uint8_t COVARIANCE_TYPE_KNOWN        = 3;

  Header header;
  NavSatStatus status;
  double latitude = 0;
  double longitude = 0;
  double altitude = 0;
  std::array<double, 9> position_covariance{};
  uint8_t position_covariance_type = 0;
};
inline void Write(cdr::Writer& w, const NavSatFix& m) {
  Write(w, m.header);
  Write(w, m.status);
  cdr::Write(w, m.latitude); cdr::Write(w, m.longitude); cdr::Write(w, m.altitude);
  Write(w, m.position_covariance);
  cdr::Write(w, m.position_covariance_type);
}
inline void Read(cdr::Reader& r, NavSatFix& m) {
  Read(r, m.header);
  Read(r, m.status);
  cdr::Read(r, m.latitude); cdr::Read(r, m.longitude); cdr::Read(r, m.altitude);
  Read(r, m.position_covariance);
  cdr::Read(r, m.position_covariance_type);
}

// ---- Scalar sensor readings ----

struct Range {
  static constexpr uint8_t ULTRASOUND = 0;
  static constexpr uint8_t INFRARED   = 1;

  Header header;
  uint8_t radiation_type = 0;
  float field_of_view = 0.f;
  float min_range = 0.f;
  float max_range = 0.f;
  float range = 0.f;
};
inline void Write(cdr::Writer& w, const Range& m) {
  Write(w, m.header);
  cdr::Write(w, m.radiation_type);
  cdr::Write(w, m.field_of_view);
  cdr::Write(w, m.min_range);
  cdr::Write(w, m.max_range);
  cdr::Write(w, m.range);
}
inline void Read(cdr::Reader& r, Range& m) {
  Read(r, m.header);
  cdr::Read(r, m.radiation_type);
  cdr::Read(r, m.field_of_view);
  cdr::Read(r, m.min_range);
  cdr::Read(r, m.max_range);
  cdr::Read(r, m.range);
}

struct Temperature {
  Header header;
  double temperature = 0;
  double variance = 0;
};
inline void Write(cdr::Writer& w, const Temperature& m) {
  Write(w, m.header);
  cdr::Write(w, m.temperature); cdr::Write(w, m.variance);
}
inline void Read(cdr::Reader& r, Temperature& m) {
  Read(r, m.header);
  cdr::Read(r, m.temperature); cdr::Read(r, m.variance);
}

struct RelativeHumidity {
  Header header;
  double relative_humidity = 0;
  double variance = 0;
};
inline void Write(cdr::Writer& w, const RelativeHumidity& m) {
  Write(w, m.header);
  cdr::Write(w, m.relative_humidity); cdr::Write(w, m.variance);
}
inline void Read(cdr::Reader& r, RelativeHumidity& m) {
  Read(r, m.header);
  cdr::Read(r, m.relative_humidity); cdr::Read(r, m.variance);
}

struct FluidPressure {
  Header header;
  double fluid_pressure = 0;
  double variance = 0;
};
inline void Write(cdr::Writer& w, const FluidPressure& m) {
  Write(w, m.header);
  cdr::Write(w, m.fluid_pressure); cdr::Write(w, m.variance);
}
inline void Read(cdr::Reader& r, FluidPressure& m) {
  Read(r, m.header);
  cdr::Read(r, m.fluid_pressure); cdr::Read(r, m.variance);
}

struct Illuminance {
  Header header;
  double illuminance = 0;
  double variance = 0;
};
inline void Write(cdr::Writer& w, const Illuminance& m) {
  Write(w, m.header);
  cdr::Write(w, m.illuminance); cdr::Write(w, m.variance);
}
inline void Read(cdr::Reader& r, Illuminance& m) {
  Read(r, m.header);
  cdr::Read(r, m.illuminance); cdr::Read(r, m.variance);
}

struct MagneticField {
  Header header;
  Vector3 magnetic_field;
  std::array<double, 9> magnetic_field_covariance{};
};
inline void Write(cdr::Writer& w, const MagneticField& m) {
  Write(w, m.header);
  Write(w, m.magnetic_field);
  Write(w, m.magnetic_field_covariance);
}
inline void Read(cdr::Reader& r, MagneticField& m) {
  Read(r, m.header);
  Read(r, m.magnetic_field);
  Read(r, m.magnetic_field_covariance);
}

struct TimeReference {
  Header header;
  Time time_ref;
  std::string source;
};
inline void Write(cdr::Writer& w, const TimeReference& m) {
  Write(w, m.header); Write(w, m.time_ref); cdr::Write(w, m.source);
}
inline void Read(cdr::Reader& r, TimeReference& m) {
  Read(r, m.header); Read(r, m.time_ref); cdr::Read(r, m.source);
}

// ---- BatteryState ----

struct BatteryState {
  static constexpr uint8_t POWER_SUPPLY_STATUS_UNKNOWN     = 0;
  static constexpr uint8_t POWER_SUPPLY_STATUS_CHARGING    = 1;
  static constexpr uint8_t POWER_SUPPLY_STATUS_DISCHARGING = 2;
  static constexpr uint8_t POWER_SUPPLY_STATUS_NOT_CHARGING = 3;
  static constexpr uint8_t POWER_SUPPLY_STATUS_FULL        = 4;

  static constexpr uint8_t POWER_SUPPLY_HEALTH_UNKNOWN     = 0;
  static constexpr uint8_t POWER_SUPPLY_HEALTH_GOOD        = 1;
  static constexpr uint8_t POWER_SUPPLY_HEALTH_OVERHEAT    = 2;
  static constexpr uint8_t POWER_SUPPLY_HEALTH_DEAD        = 3;
  static constexpr uint8_t POWER_SUPPLY_HEALTH_OVERVOLTAGE = 4;
  static constexpr uint8_t POWER_SUPPLY_HEALTH_UNSPEC_FAILURE = 5;
  static constexpr uint8_t POWER_SUPPLY_HEALTH_COLD        = 6;
  static constexpr uint8_t POWER_SUPPLY_HEALTH_WATCHDOG_TIMER_EXPIRE = 7;
  static constexpr uint8_t POWER_SUPPLY_HEALTH_SAFETY_TIMER_EXPIRE = 8;

  static constexpr uint8_t POWER_SUPPLY_TECHNOLOGY_UNKNOWN = 0;
  static constexpr uint8_t POWER_SUPPLY_TECHNOLOGY_NIMH    = 1;
  static constexpr uint8_t POWER_SUPPLY_TECHNOLOGY_LION    = 2;
  static constexpr uint8_t POWER_SUPPLY_TECHNOLOGY_LIPO    = 3;
  static constexpr uint8_t POWER_SUPPLY_TECHNOLOGY_LIFE    = 4;
  static constexpr uint8_t POWER_SUPPLY_TECHNOLOGY_NICD    = 5;
  static constexpr uint8_t POWER_SUPPLY_TECHNOLOGY_LIMN    = 6;

  Header header;
  float voltage = 0.f;
  float temperature = 0.f;
  float current = 0.f;
  float charge = 0.f;
  float capacity = 0.f;
  float design_capacity = 0.f;
  float percentage = 0.f;
  uint8_t power_supply_status = 0;
  uint8_t power_supply_health = 0;
  uint8_t power_supply_technology = 0;
  bool present = false;
  std::vector<float> cell_voltage;
  std::vector<float> cell_temperature;
  std::string location;
  std::string serial_number;
};
inline void Write(cdr::Writer& w, const BatteryState& m) {
  Write(w, m.header);
  cdr::Write(w, m.voltage); cdr::Write(w, m.temperature); cdr::Write(w, m.current);
  cdr::Write(w, m.charge); cdr::Write(w, m.capacity); cdr::Write(w, m.design_capacity);
  cdr::Write(w, m.percentage);
  cdr::Write(w, m.power_supply_status);
  cdr::Write(w, m.power_supply_health);
  cdr::Write(w, m.power_supply_technology);
  cdr::Write(w, m.present);
  Write(w, m.cell_voltage);
  Write(w, m.cell_temperature);
  cdr::Write(w, m.location);
  cdr::Write(w, m.serial_number);
}
inline void Read(cdr::Reader& r, BatteryState& m) {
  Read(r, m.header);
  cdr::Read(r, m.voltage); cdr::Read(r, m.temperature); cdr::Read(r, m.current);
  cdr::Read(r, m.charge); cdr::Read(r, m.capacity); cdr::Read(r, m.design_capacity);
  cdr::Read(r, m.percentage);
  cdr::Read(r, m.power_supply_status);
  cdr::Read(r, m.power_supply_health);
  cdr::Read(r, m.power_supply_technology);
  cdr::Read(r, m.present);
  Read(r, m.cell_voltage);
  Read(r, m.cell_temperature);
  cdr::Read(r, m.location);
  cdr::Read(r, m.serial_number);
}

// ---- Joy ----

struct Joy {
  Header header;
  std::vector<float> axes;
  std::vector<int32_t> buttons;
};
inline void Write(cdr::Writer& w, const Joy& m) {
  Write(w, m.header); Write(w, m.axes); Write(w, m.buttons);
}
inline void Read(cdr::Reader& r, Joy& m) {
  Read(r, m.header); Read(r, m.axes); Read(r, m.buttons);
}

// ---- ChannelFloat32 + PointCloud (legacy) ----

struct ChannelFloat32 {
  std::string name;
  std::vector<float> values;
};
inline void Write(cdr::Writer& w, const ChannelFloat32& m) {
  cdr::Write(w, m.name); Write(w, m.values);
}
inline void Read(cdr::Reader& r, ChannelFloat32& m) {
  cdr::Read(r, m.name); Read(r, m.values);
}

struct PointCloud {
  Header header;
  std::vector<Point32> points;
  std::vector<ChannelFloat32> channels;
};
inline void Write(cdr::Writer& w, const PointCloud& m) {
  Write(w, m.header); Write(w, m.points); Write(w, m.channels);
}
inline void Read(cdr::Reader& r, PointCloud& m) {
  Read(r, m.header); Read(r, m.points); Read(r, m.channels);
}

}  // namespace talos::msgs

#endif  // TALOSOS_MSGS_SENSOR_MSGS_H_
