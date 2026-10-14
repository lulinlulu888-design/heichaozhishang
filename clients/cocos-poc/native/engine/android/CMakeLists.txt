cmake_minimum_required(VERSION 3.8)

option(APP_NAME "Project Name" "hczs-cocos-poc")
project(${APP_NAME} CXX)
set(CC_LIB_NAME cocos)
set(CC_PROJECT_DIR ${CMAKE_CURRENT_LIST_DIR})
set(CC_PROJ_SOURCES)
set(CC_COMMON_SOURCES)
set(CC_ALL_SOURCES)

include(${CMAKE_CURRENT_LIST_DIR}/../common/CMakeLists.txt)

cc_android_before_target(${CC_LIB_NAME})
add_library(${CC_LIB_NAME} SHARED ${CC_ALL_SOURCES})
cc_android_after_target(${CC_LIB_NAME})

# NDK r27's flexible-page option sets max-page-size only. Set common-page-size
# too so the GNU_RELRO range ends on a 16 KB boundary (Android guidance).
target_link_options(${CC_LIB_NAME} PRIVATE
    "-Wl,-z,max-page-size=16384"
    "-Wl,-z,common-page-size=16384"
)
