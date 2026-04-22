talosos_add_messages(
  NAME add_two_ints
  FILES
    msg/AddTwoIntsRequest.msg
    msg/AddTwoIntsResponse.msg
)

add_executable(add_two_ints_server add_two_ints_server.cc)
target_link_libraries(add_two_ints_server
  PRIVATE TalosOS::talosos add_two_ints_msgs)

add_executable(add_two_ints_client add_two_ints_client.cc)
target_link_libraries(add_two_ints_client
  PRIVATE TalosOS::talosos add_two_ints_msgs)
