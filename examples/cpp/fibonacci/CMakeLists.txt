talosos_add_messages(
  NAME fibonacci
  FILES
    msg/FibonacciGoal.msg
    msg/FibonacciFeedback.msg
    msg/FibonacciResult.msg
)

add_executable(fibonacci_server fibonacci_server.cc)
target_link_libraries(fibonacci_server
  PRIVATE TalosOS::talosos fibonacci_msgs)

add_executable(fibonacci_client fibonacci_client.cc)
target_link_libraries(fibonacci_client
  PRIVATE TalosOS::talosos fibonacci_msgs)
