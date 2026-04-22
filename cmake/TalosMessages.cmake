# Generate C++ headers from a set of .msg files using talos_msg_gen.py.
#
# Signature:
#   talosos_add_messages(
#     NAME <package>                 # logical package; becomes talos::<package>
#     FILES <a.msg> <b.msg> ...
#     [OUT_DIR <dir>]                # default: ${CMAKE_CURRENT_BINARY_DIR}/msg_gen
#   )
#
# Creates an INTERFACE target <package>_msgs that exposes the include directory
# where the generated headers live. Headers are placed under
#   ${OUT_DIR}/talos/<package>/<MsgName>.h
# so users can include them as "talos/<package>/MsgName.h".

find_package(Python3 COMPONENTS Interpreter REQUIRED)

# Locate talos_msg_gen.py. Two search orders depending on whether we're being
# consumed from a build-tree `find_package` or from an installed TalosOS.
set(_talosos_msg_gen_candidates
  "${CMAKE_CURRENT_LIST_DIR}/tools/talos_msg_gen.py"          # installed
  "${CMAKE_CURRENT_LIST_DIR}/../tools/talos_msg_gen.py"       # in-tree
)
foreach(_cand IN LISTS _talosos_msg_gen_candidates)
  if(EXISTS "${_cand}")
    set(TALOSOS_MSG_GEN_SCRIPT "${_cand}" CACHE FILEPATH
        "Path to talos_msg_gen.py")
    break()
  endif()
endforeach()
if(NOT TALOSOS_MSG_GEN_SCRIPT)
  message(FATAL_ERROR
    "TalosMessages.cmake: cannot locate talos_msg_gen.py near ${CMAKE_CURRENT_LIST_DIR}")
endif()

function(talosos_add_messages)
  set(options "")
  set(one_value_args NAME OUT_DIR)
  set(multi_value_args FILES)
  cmake_parse_arguments(TALOSMSG "${options}" "${one_value_args}"
                         "${multi_value_args}" ${ARGN})

  if(NOT TALOSMSG_NAME)
    message(FATAL_ERROR "talosos_add_messages: NAME is required")
  endif()
  if(NOT TALOSMSG_FILES)
    message(FATAL_ERROR "talosos_add_messages: FILES is required")
  endif()
  if(NOT TALOSMSG_OUT_DIR)
    set(TALOSMSG_OUT_DIR "${CMAKE_CURRENT_BINARY_DIR}/msg_gen")
  endif()

  set(_include_dir "${TALOSMSG_OUT_DIR}")
  set(_pkg_out_dir "${_include_dir}/talos/${TALOSMSG_NAME}")
  file(MAKE_DIRECTORY "${_pkg_out_dir}")

  set(_generated_headers "")
  foreach(msg_file IN LISTS TALOSMSG_FILES)
    if(NOT IS_ABSOLUTE "${msg_file}")
      set(_abs_msg "${CMAKE_CURRENT_SOURCE_DIR}/${msg_file}")
    else()
      set(_abs_msg "${msg_file}")
    endif()
    get_filename_component(_msg_stem "${msg_file}" NAME_WE)
    set(_out_header "${_pkg_out_dir}/${_msg_stem}.h")

    add_custom_command(
      OUTPUT "${_out_header}"
      COMMAND "${Python3_EXECUTABLE}" "${TALOSOS_MSG_GEN_SCRIPT}"
              --package "${TALOSMSG_NAME}"
              --input  "${_abs_msg}"
              --output "${_out_header}"
      DEPENDS "${_abs_msg}" "${TALOSOS_MSG_GEN_SCRIPT}"
      COMMENT "Generating talos::${TALOSMSG_NAME}::${_msg_stem}"
      VERBATIM
    )
    list(APPEND _generated_headers "${_out_header}")
  endforeach()

  set(_target_name "${TALOSMSG_NAME}_msgs")
  add_custom_target("${_target_name}_gen" DEPENDS ${_generated_headers})

  if(NOT TARGET "${_target_name}")
    add_library("${_target_name}" INTERFACE)
  endif()
  target_include_directories("${_target_name}" INTERFACE "${_include_dir}")
  target_link_libraries("${_target_name}" INTERFACE TalosOS::talosos)
  add_dependencies("${_target_name}" "${_target_name}_gen")
endfunction()
