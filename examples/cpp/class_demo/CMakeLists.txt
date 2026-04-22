# Example: encapsulating TalosOS APIs inside a C++ class.

add_library(class_demo_chatter STATIC
  src/chatter_node.cc
)
target_include_directories(class_demo_chatter PUBLIC include)
target_link_libraries(class_demo_chatter PUBLIC TalosOS::talosos)

add_executable(chatter_class_node src/chatter_main.cc)
target_link_libraries(chatter_class_node PRIVATE class_demo_chatter)

add_executable(chatter_class_client src/chatter_client.cc)
target_link_libraries(chatter_class_client PRIVATE class_demo_chatter)
