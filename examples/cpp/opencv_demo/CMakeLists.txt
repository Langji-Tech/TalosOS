# OpenCV bridge demo — requires OpenCV (>= 4).

find_package(OpenCV QUIET COMPONENTS core imgcodecs imgproc highgui)

if(NOT OpenCV_FOUND)
  message(STATUS "opencv_demo: OpenCV not found, skipping examples")
  return()
endif()

add_executable(cv_publisher cv_publisher.cc)
target_link_libraries(cv_publisher PRIVATE TalosOS::talosos ${OpenCV_LIBS})
target_include_directories(cv_publisher PRIVATE ${OpenCV_INCLUDE_DIRS})

add_executable(cv_subscriber cv_subscriber.cc)
target_link_libraries(cv_subscriber PRIVATE TalosOS::talosos ${OpenCV_LIBS})
target_include_directories(cv_subscriber PRIVATE ${OpenCV_INCLUDE_DIRS})
