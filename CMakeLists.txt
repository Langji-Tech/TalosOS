cmake_minimum_required(VERSION 3.16)

project(TalosOS VERSION 1.0.0 LANGUAGES CXX)

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)
include(${CMAKE_CURRENT_SOURCE_DIR}/cmake/TalosMessages.cmake)

option(TALOSOS_BUILD_EXAMPLES "Build TalosOS examples" ON)
option(TALOSOS_USE_BUNDLED_ZENOH "Use bundled zenoh-cpp checkout when available" ON)
option(TALOSOS_BUILD_PYTHON "Build TalosOS Python 3 bindings" ON)
option(TALOSOS_ENABLE_PCL "Enable optional PCL-based adapters and examples" OFF)
set(TALOSOS_USING_BUNDLED_ZENOH OFF)
set(TALOSOS_PYTHON_SITE_DIR_REL "")
set(TALOSOS_COMPLETION_BASH_REL "")
set(TALOSOS_COMPLETION_ZSH_REL "")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Avoid rediscovering our own install tree on re-configures — the partial
# zenoh-cpp install that the bundled subdirectory sprays into our prefix would
# otherwise confuse find_package(zenohcxx).
if(DEFINED CMAKE_INSTALL_PREFIX AND IS_DIRECTORY "${CMAKE_INSTALL_PREFIX}")
  list(APPEND CMAKE_IGNORE_PATH "${CMAKE_INSTALL_PREFIX}")
endif()

if(NOT TALOSOS_USE_BUNDLED_ZENOH)
  find_package(zenohc QUIET)
  find_package(zenohcxx QUIET)
endif()

if(TALOSOS_USE_BUNDLED_ZENOH AND NOT TARGET zenohc::lib AND NOT TARGET zenohcxx::zenohc)
  set(_TALOSOS_BUNDLED_ZENOHC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/zenoh-cpp/zenoh-c")
  set(_TALOSOS_BUNDLED_ZENOHCXX_DIR "${CMAKE_CURRENT_SOURCE_DIR}/zenoh-cpp")

  if(EXISTS "${_TALOSOS_BUNDLED_ZENOHC_DIR}/CMakeLists.txt" AND EXISTS "${_TALOSOS_BUNDLED_ZENOHCXX_DIR}/CMakeLists.txt")
    set(BUILD_SHARED_LIBS ON CACHE BOOL "" FORCE)
    set(ZENOHC_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
    set(ZENOHC_BUILD_TESTS OFF CACHE BOOL "" FORCE)
    set(ZENOHC_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
    set(ZENOHC_BUILD_WITH_UNSTABLE_API ON CACHE BOOL "" FORCE)
    set(ZENOHC_BUILD_WITH_SHARED_MEMORY ON CACHE BOOL "" FORCE)
    set(ZENOHCXX_ENABLE_TESTS OFF CACHE BOOL "" FORCE)
    set(ZENOHCXX_ENABLE_EXAMPLES OFF CACHE BOOL "" FORCE)
    set(ZENOHCXX_EXAMPLES_PROTOBUF OFF CACHE BOOL "" FORCE)
    add_subdirectory("${_TALOSOS_BUNDLED_ZENOHC_DIR}" "${CMAKE_CURRENT_BINARY_DIR}/third_party/zenoh-c")
    add_subdirectory("${_TALOSOS_BUNDLED_ZENOHCXX_DIR}" "${CMAKE_CURRENT_BINARY_DIR}/third_party/zenoh-cpp")
    set(TALOSOS_USING_BUNDLED_ZENOH ON)
  endif()
endif()

if(NOT TARGET zenohc::lib OR NOT TARGET zenohcxx::zenohc)
  set(_TALOSOS_ROS2_ZENOH_CMAKE_PATH "/opt/ros/$ENV{ROS_DISTRO}/opt/zenoh_cpp_vendor/lib/cmake")
  if(EXISTS "${_TALOSOS_ROS2_ZENOH_CMAKE_PATH}")
    list(PREPEND CMAKE_PREFIX_PATH "${_TALOSOS_ROS2_ZENOH_CMAKE_PATH}")
  endif()

  find_package(zenoh_cpp_vendor QUIET)

  if(NOT TARGET zenohc::lib)
    find_package(zenohc QUIET)
  endif()
  if(NOT TARGET zenohcxx::zenohc)
    find_package(zenohcxx QUIET)
  endif()
endif()

if(NOT TARGET zenohc::lib)
  message(FATAL_ERROR "TalosOS requires zenohc::lib. Install zenohc, provide zenoh-cpp with its zenoh-c submodule, or use ROS zenoh_cpp_vendor.")
endif()

if(NOT TARGET zenohcxx::zenohc)
  message(FATAL_ERROR "TalosOS requires zenohcxx::zenohc. Install zenohcxx, provide a bundled zenoh-cpp checkout, or use ROS zenoh_cpp_vendor.")
endif()

find_package(Threads REQUIRED)
find_package(Eigen3 REQUIRED)
find_package(OpenCV QUIET COMPONENTS core imgcodecs)
if(TALOSOS_ENABLE_PCL)
  find_package(MPI QUIET COMPONENTS C)
  find_package(PCL QUIET COMPONENTS common io)
endif()
if(TALOSOS_BUILD_PYTHON)
  find_package(Python3 QUIET COMPONENTS Interpreter Development.Module)
  if(Python3_Interpreter_FOUND)
    execute_process(
      COMMAND "${Python3_EXECUTABLE}" -c
              "import pybind11, sys; sys.stdout.write(pybind11.get_cmake_dir())"
      OUTPUT_VARIABLE _pybind11_dir
      RESULT_VARIABLE _pybind11_rc
    )
    if(_pybind11_rc EQUAL 0 AND _pybind11_dir)
      list(PREPEND CMAKE_PREFIX_PATH "${_pybind11_dir}")
      find_package(pybind11 QUIET CONFIG)
    endif()
  endif()
endif()

add_library(talosos SHARED
  src/node.cc
  src/logging.cc
)

add_library(TalosOS::talosos ALIAS talosos)

target_include_directories(talosos
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
)

target_link_libraries(talosos
  PUBLIC
    Eigen3::Eigen
    pthread
  PRIVATE
    zenohcxx::zenohc
    Threads::Threads
)

set_target_properties(talosos PROPERTIES
  OUTPUT_NAME talosos
  SOVERSION ${PROJECT_VERSION_MAJOR}
  VERSION   ${PROJECT_VERSION}
  # Look for sibling libs (libzenohc.so) next to libtalosos.so at runtime
  # so downstream binaries don't need LD_LIBRARY_PATH or an extra rpath.
  INSTALL_RPATH "\$ORIGIN"
  # Same for the in-tree build so tests + examples run directly.
  BUILD_WITH_INSTALL_RPATH FALSE
  BUILD_RPATH "\$ORIGIN"
)

if(TALOSOS_BUILD_PYTHON AND pybind11_FOUND AND Python3_Development.Module_FOUND)
  pybind11_add_module(_talosos_runtime MODULE src/python/bindings.cc)
  target_link_libraries(_talosos_runtime PRIVATE talosos)
  set_target_properties(_talosos_runtime PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/python"
  )
  set(TALOSOS_RUNTIME_BUILT ON)
endif()

add_executable(talosos_tool src/tool/talosos_tool.cc)
target_link_libraries(talosos_tool PRIVATE
  zenohcxx::zenohc
  Threads::Threads
)
set_target_properties(talosos_tool PROPERTIES
  OUTPUT_NAME talosos_tool
)

install(TARGETS talosos_tool
  RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)

if(TALOSOS_BUILD_EXAMPLES)
  add_subdirectory(examples/cpp)
endif()

# ----------------------------------------------------------------------------
# Install rules
# ----------------------------------------------------------------------------

install(TARGETS talosos
  EXPORT TalosOSTargets
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
  ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
  RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)

# Ship libzenohc.so alongside libtalosos.so when we built zenoh from the bundled
# source — the Rust-built artifact lives outside the usual install() tree.
if(TALOSOS_USING_BUNDLED_ZENOH)
  set(_TALOSOS_ZENOHC_SO
      "${CMAKE_CURRENT_BINARY_DIR}/third_party/zenoh-c/release/target/release/libzenohc.so")
  if(EXISTS "${_TALOSOS_ZENOHC_SO}")
    install(FILES "${_TALOSOS_ZENOHC_SO}"
      DESTINATION ${CMAKE_INSTALL_LIBDIR})
  else()
    install(CODE "
      set(_src \"${CMAKE_CURRENT_BINARY_DIR}/third_party/zenoh-c/release/target/release/libzenohc.so\")
      if(EXISTS \"\${_src}\")
        file(INSTALL \"\${_src}\" DESTINATION \"\${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_LIBDIR}\")
      endif()")
  endif()
endif()

install(DIRECTORY include/
  DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
  FILES_MATCHING PATTERN "*.h"
)

set(TALOSOS_CMAKE_CONFIG_DIR "${CMAKE_INSTALL_LIBDIR}/cmake/TalosOS")

install(EXPORT TalosOSTargets
  FILE TalosOSTargets.cmake
  NAMESPACE TalosOS::
  DESTINATION ${TALOSOS_CMAKE_CONFIG_DIR}
)

configure_package_config_file(cmake/TalosOSConfig.cmake.in
  ${CMAKE_CURRENT_BINARY_DIR}/TalosOSConfig.cmake
  INSTALL_DESTINATION ${TALOSOS_CMAKE_CONFIG_DIR}
)

write_basic_package_version_file(
  ${CMAKE_CURRENT_BINARY_DIR}/TalosOSConfigVersion.cmake
  VERSION ${PROJECT_VERSION}
  COMPATIBILITY SameMinorVersion
)

install(FILES
  ${CMAKE_CURRENT_BINARY_DIR}/TalosOSConfig.cmake
  ${CMAKE_CURRENT_BINARY_DIR}/TalosOSConfigVersion.cmake
  cmake/TalosMessages.cmake
  DESTINATION ${TALOSOS_CMAKE_CONFIG_DIR}
)

# Co-locate the .msg generator with the CMake config so TalosMessages.cmake can
# find it via ${CMAKE_CURRENT_LIST_DIR}/tools/... after install.
install(PROGRAMS tools/talos_msg_gen.py
  DESTINATION ${TALOSOS_CMAKE_CONFIG_DIR}/tools
)

# ---- Python package + talos CLI wrapper ----
if(TALOSOS_BUILD_PYTHON AND Python3_Interpreter_FOUND)
  # Decide where to drop the Python package + pybind11 extension:
  #
  #   venv / conda / 私有 prefix —— `Python3_EXECUTABLE` 位于
  #       `CMAKE_INSTALL_PREFIX` 之下 —— 用标准
  #       `lib/pythonX.Y/site-packages`，这是 venv/conda Python 原生搜索的
  #       路径。
  #
  #   系统安装（Debian/Ubuntu 到 /opt/talosos）—— Python 不会版本中立地搜
  #       `lib/python3.X/site-packages`；Debian 打过补丁把
  #       `lib/python3/dist-packages` 加到了 sys.path，用这个可以一份拷
  #       贝同时给 3.10 / 3.12 用。
  #
  # 显式覆盖：-DTALOSOS_PYTHON_SITE_DIR_REL=lib/mypython/site-packages
  if(NOT DEFINED TALOSOS_PYTHON_SITE_DIR_REL OR TALOSOS_PYTHON_SITE_DIR_REL STREQUAL "")
    # 用 Python 自己的 `sys.prefix` 判断是不是 venv / conda —— 这对
    # symlink / uv 内核都正确（不能用 Python3_EXECUTABLE 的 REALPATH，
    # 因为 uv 的 .venv/bin/python 会解到 venv 外面的真 python）。
    execute_process(
      COMMAND "${Python3_EXECUTABLE}" -c
              "import os,sys; print(os.path.realpath(sys.prefix))"
      OUTPUT_VARIABLE _py_sys_prefix
      OUTPUT_STRIP_TRAILING_WHITESPACE
      RESULT_VARIABLE _py_rc)
    get_filename_component(_prefix_real "${CMAKE_INSTALL_PREFIX}" REALPATH)
    if(_py_rc EQUAL 0 AND _py_sys_prefix STREQUAL _prefix_real)
      set(TALOSOS_PYTHON_SITE_DIR_REL
          "lib/python${Python3_VERSION_MAJOR}.${Python3_VERSION_MINOR}/site-packages")
      message(STATUS
        "TalosOS Python: venv/conda detected (sys.prefix=${_py_sys_prefix}) → ${TALOSOS_PYTHON_SITE_DIR_REL}")
    else()
      set(TALOSOS_PYTHON_SITE_DIR_REL "lib/python3/dist-packages")
      message(STATUS
        "TalosOS Python: system install → ${TALOSOS_PYTHON_SITE_DIR_REL}")
    endif()
  else()
    message(STATUS
      "TalosOS Python: using override TALOSOS_PYTHON_SITE_DIR_REL=${TALOSOS_PYTHON_SITE_DIR_REL}")
  endif()

  install(DIRECTORY python/talosos/
    DESTINATION ${TALOSOS_PYTHON_SITE_DIR_REL}/talosos
    FILES_MATCHING
      PATTERN "*.py"
      PATTERN "__pycache__" EXCLUDE
  )

  if(TALOSOS_RUNTIME_BUILT)
    install(TARGETS _talosos_runtime
      LIBRARY DESTINATION ${TALOSOS_PYTHON_SITE_DIR_REL}/talosos
    )
  endif()
endif()

# Shell completion (installed regardless of Python build option — completion is
# pure shell and works against whatever `talos` resolves to on PATH).
set(TALOSOS_COMPLETION_BASH_REL "share/talosos/talos-completion.bash")
set(TALOSOS_COMPLETION_ZSH_REL  "share/talosos/talos-completion.zsh")

configure_file(cmake/talos-completion.bash.in
  ${CMAKE_CURRENT_BINARY_DIR}/talos-completion.bash @ONLY)
configure_file(cmake/talos-completion.zsh.in
  ${CMAKE_CURRENT_BINARY_DIR}/talos-completion.zsh @ONLY)

install(FILES
  ${CMAKE_CURRENT_BINARY_DIR}/talos-completion.bash
  ${CMAKE_CURRENT_BINARY_DIR}/talos-completion.zsh
  DESTINATION share/talosos
)

# talos CLI launcher (a thin Python shim generated from cmake/talos.in).
configure_file(cmake/talos.in
  ${CMAKE_CURRENT_BINARY_DIR}/talos @ONLY)
install(PROGRAMS ${CMAKE_CURRENT_BINARY_DIR}/talos
  DESTINATION ${CMAKE_INSTALL_BINDIR}
)

# Setup scripts — placed at prefix root so `source /opt/talosos/setup.bash`
# just works.
configure_file(cmake/setup.sh.in   ${CMAKE_CURRENT_BINARY_DIR}/setup.sh   @ONLY)
configure_file(cmake/setup.bash.in ${CMAKE_CURRENT_BINARY_DIR}/setup.bash @ONLY)
configure_file(cmake/setup.zsh.in  ${CMAKE_CURRENT_BINARY_DIR}/setup.zsh  @ONLY)

install(FILES
  ${CMAKE_CURRENT_BINARY_DIR}/setup.sh
  ${CMAKE_CURRENT_BINARY_DIR}/setup.bash
  ${CMAKE_CURRENT_BINARY_DIR}/setup.zsh
  DESTINATION .
)

# Ship Python example scripts so users can copy-run them post-install.
install(DIRECTORY examples/python/
  DESTINATION share/talosos/examples/python
  FILES_MATCHING
    PATTERN "*.py"
    PATTERN "*.md"
    PATTERN "__pycache__" EXCLUDE
)

# ----------------------------------------------------------------------------
# CPack — Debian package generator (Ubuntu 20.04+, dpkg-based distros)
# ----------------------------------------------------------------------------
#
# Invoke via:
#   scripts/make_deb.sh                     # wraps the below
#   # or manually:
#   cmake -S . -B build -DCMAKE_INSTALL_PREFIX=/opt/talosos -DCMAKE_BUILD_TYPE=Release
#   cmake --build build -j
#   cd build && cpack -G DEB
#
# The .deb embeds Python extensions with the build-host's Python ABI tag;
# build the package on the same Ubuntu release you plan to install on
# (20.04 → Python 3.8, 22.04 → 3.10, 24.04 → 3.12). See docker/ for a
# reproducible Ubuntu 20.04 build environment.

if(UNIX AND NOT APPLE)
  set(CPACK_GENERATOR "DEB")
  set(CPACK_PACKAGE_NAME "talosos")
  set(CPACK_PACKAGE_VERSION "${PROJECT_VERSION}")
  set(CPACK_PACKAGE_VENDOR "Hangzhou Langji Intelligent Technology Co., Ltd.")
  set(CPACK_PACKAGE_CONTACT "杭州朗极智能科技有限公司 <support@langji-robotics.com>")
  set(CPACK_PACKAGE_HOMEPAGE_URL "https://example.com/talosos")

  set(CPACK_PACKAGE_DESCRIPTION_SUMMARY
      "Lightweight ROS1-style robot OS on zenoh-cpp")
  set(CPACK_PACKAGE_DESCRIPTION
      "TalosOS is a lightweight ROS1-style robot operating system built
 on Eclipse Zenoh for transport. Supplies Publisher / Subscription /
 Service / Action primitives, CDR-compatible messages (interoperable
 with ROS2 and Foxglove), a talos CLI (pkg / build / run / topic /
 service / launch / plot / viz / rqt), and a pybind11 Python runtime.
 Installs under /opt/talosos; source setup.bash to activate.")

  # Package metadata.
  set(CPACK_DEBIAN_PACKAGE_SECTION "science")
  set(CPACK_DEBIAN_PACKAGE_PRIORITY "optional")

  # Architecture — ask dpkg for the native triple.
  execute_process(
    COMMAND dpkg --print-architecture
    OUTPUT_VARIABLE CPACK_DEBIAN_PACKAGE_ARCHITECTURE
    OUTPUT_STRIP_TRAILING_WHITESPACE
    ERROR_QUIET
  )
  if(NOT CPACK_DEBIAN_PACKAGE_ARCHITECTURE)
    set(CPACK_DEBIAN_PACKAGE_ARCHITECTURE "amd64")
  endif()

  # Tag the .deb with ubuntu release codename so multiple builds can coexist.
  execute_process(
    COMMAND lsb_release -cs
    OUTPUT_VARIABLE _TALOSOS_UBUNTU_CODENAME
    OUTPUT_STRIP_TRAILING_WHITESPACE
    ERROR_QUIET
  )
  if(_TALOSOS_UBUNTU_CODENAME)
    set(CPACK_PACKAGE_FILE_NAME
        "${CPACK_PACKAGE_NAME}_${CPACK_PACKAGE_VERSION}-${_TALOSOS_UBUNTU_CODENAME}_${CPACK_DEBIAN_PACKAGE_ARCHITECTURE}")
  else()
    set(CPACK_PACKAGE_FILE_NAME
        "${CPACK_PACKAGE_NAME}_${CPACK_PACKAGE_VERSION}_${CPACK_DEBIAN_PACKAGE_ARCHITECTURE}")
  endif()

  # Hard runtime dependencies. shlibdeps adds precise libc / libstdc++ pins.
  set(CPACK_DEBIAN_PACKAGE_DEPENDS
      "python3 (>= 3.8), python3-yaml")
  set(CPACK_DEBIAN_PACKAGE_RECOMMENDS
      "python3-pybind11, python3-matplotlib, python3-pyqt5, libopencv-dev, cmake (>= 3.16)")
  set(CPACK_DEBIAN_PACKAGE_SUGGESTS
      "python3-numpy, rustc")
  set(CPACK_DEBIAN_PACKAGE_SHLIBDEPS ON)

  # Postinst / postrm for user-friendly install output + ldconfig hook.
  configure_file(${CMAKE_CURRENT_SOURCE_DIR}/cmake/deb-postinst.in
                 ${CMAKE_CURRENT_BINARY_DIR}/deb/postinst @ONLY)
  configure_file(${CMAKE_CURRENT_SOURCE_DIR}/cmake/deb-postrm.in
                 ${CMAKE_CURRENT_BINARY_DIR}/deb/postrm @ONLY)
  set(CPACK_DEBIAN_PACKAGE_CONTROL_EXTRA
      "${CMAKE_CURRENT_BINARY_DIR}/deb/postinst;${CMAKE_CURRENT_BINARY_DIR}/deb/postrm")

  # No compression flag default; use xz for smaller .deb.
  set(CPACK_DEBIAN_COMPRESSION_TYPE "xz")

  # Keep TalosOS self-contained under /opt/talosos rather than FHS-sprayed
  # across /usr. Matches what scripts/install_opt.sh does for source installs.
  set(CPACK_PACKAGING_INSTALL_PREFIX "/opt/talosos")

  include(CPack)
endif()
