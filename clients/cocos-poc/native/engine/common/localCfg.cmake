# Keep the local proof executable from opening the template's remote V8
# debugger listener. This is loaded after Creator's generated cfg.cmake.
set(USE_V8_DEBUGGER OFF CACHE BOOL "Disable remote JavaScript debugger" FORCE)
set(USE_V8_DEBUGGER_FORCE OFF CACHE BOOL "Disable forced JavaScript debugger" FORCE)
