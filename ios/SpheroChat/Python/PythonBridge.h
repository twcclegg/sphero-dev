// The app's embedded Python (sphero_dev.app) and the Bluetooth module it uses.
// Swift calls these; PythonBridge.c implements them with the CPython C API.
#ifndef PythonBridge_h
#define PythonBridge_h

#include <stddef.h>
#include <stdint.h>

/// Start Python. `home` is the bundled standard library's prefix, `paths` a
/// NUL-separated list of extra directories for sys.path (the app's code and
/// packages). Returns NULL on success, or a malloc'd error message.
char *sd_python_start(const char *home, const char *stdlib, const char *paths);

/// Call `sphero_dev.app.<function>(argument)` (argument may be NULL for no
/// arguments). Returns its string result, malloc'd; free it with `free`. Safe
/// from any thread; blocks until the Python call returns.
char *sd_python_call(const char *function, const char *argument);

/// Pass a notification from the robot to Python (sphero_dev.ios_adapter.on_notify).
void sd_python_notify(const char *address, const char *uuid, const uint8_t *data, size_t length);

// Implemented in Swift (BluetoothBridge.swift) with @_cdecl. Each blocks until
// done. Results and errors are malloc'd strings, or NULL for success.
char *sd_ble_scan(double timeout);                       // JSON [{"name","address"}]
char *sd_ble_connect(const char *address);               // NULL or error
void sd_ble_disconnect(const char *address);
char *sd_ble_subscribe(const char *address, const char *uuid);
char *sd_ble_write(const char *address, const char *uuid, const uint8_t *data, size_t length);

#endif
