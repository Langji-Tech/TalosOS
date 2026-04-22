add_executable(talker talker.cc)
target_link_libraries(talker PRIVATE TalosOS::talosos)

add_executable(listener listener.cc)
target_link_libraries(listener PRIVATE TalosOS::talosos)

add_executable(msg_roundtrip msg_roundtrip.cc)
target_link_libraries(msg_roundtrip PRIVATE TalosOS::talosos)

add_subdirectory(add_two_ints)
add_subdirectory(fibonacci)
add_subdirectory(class_demo)
add_subdirectory(image_bench)
add_subdirectory(opencv_demo)
