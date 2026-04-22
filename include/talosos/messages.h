#ifndef TALOSOS_MESSAGES_H_
#define TALOSOS_MESSAGES_H_

// Umbrella include: pulls in Time/Duration and every message subfamily.
// Prefer including only what you need from the talosos/msgs/*.h subheaders
// to keep compile times reasonable in large translation units.

#include "talosos/time.h"
#include "talosos/msgs/std_msgs.h"
#include "talosos/msgs/geometry_msgs.h"
#include "talosos/msgs/sensor_msgs.h"
#include "talosos/msgs/nav_msgs.h"
#include "talosos/msgs/tf2_msgs.h"
#include "talosos/msgs/visualization_msgs.h"
#include "talosos/msgs/pcl_msgs.h"
#include "talosos/msgs/octomap_msgs.h"

#endif  // TALOSOS_MESSAGES_H_
