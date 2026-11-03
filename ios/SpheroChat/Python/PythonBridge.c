// Embeds CPython (from Python.xcframework, see ios/README.md) and gives it a
// built-in module, _sphero_ble, whose functions call the Swift Bluetooth code.
#define PY_SSIZE_T_CLEAN
#include <Python/Python.h>
#include <stdlib.h>
#include <string.h>

#include "PythonBridge.h"

// --- _sphero_ble: Python -> Swift ---------------------------------------------

// Turn a Swift result (malloc'd error string or NULL) into None or an exception.
static PyObject *result_or_raise(char *error) {
    if (error == NULL) Py_RETURN_NONE;
    PyErr_SetString(PyExc_OSError, error);
    free(error);
    return NULL;
}

static PyObject *ble_scan(PyObject *self, PyObject *args) {
    double timeout;
    if (!PyArg_ParseTuple(args, "d", &timeout)) return NULL;
    char *json;
    Py_BEGIN_ALLOW_THREADS  // Bluetooth calls block; let other Python threads run
    json = sd_ble_scan(timeout);
    Py_END_ALLOW_THREADS
    if (json == NULL) return PyUnicode_FromString("[]");
    PyObject *s = PyUnicode_FromString(json);
    free(json);
    return s;
}

static PyObject *ble_connect(PyObject *self, PyObject *args) {
    const char *address;
    if (!PyArg_ParseTuple(args, "s", &address)) return NULL;
    char *error;
    Py_BEGIN_ALLOW_THREADS
    error = sd_ble_connect(address);
    Py_END_ALLOW_THREADS
    return result_or_raise(error);
}

static PyObject *ble_disconnect(PyObject *self, PyObject *args) {
    const char *address;
    if (!PyArg_ParseTuple(args, "s", &address)) return NULL;
    Py_BEGIN_ALLOW_THREADS
    sd_ble_disconnect(address);
    Py_END_ALLOW_THREADS
    Py_RETURN_NONE;
}

static PyObject *ble_subscribe(PyObject *self, PyObject *args) {
    const char *address, *uuid;
    if (!PyArg_ParseTuple(args, "ss", &address, &uuid)) return NULL;
    char *error;
    Py_BEGIN_ALLOW_THREADS
    error = sd_ble_subscribe(address, uuid);
    Py_END_ALLOW_THREADS
    return result_or_raise(error);
}

static PyObject *ble_write(PyObject *self, PyObject *args) {
    const char *address, *uuid;
    Py_buffer data;
    if (!PyArg_ParseTuple(args, "ssy*", &address, &uuid, &data)) return NULL;
    char *error;
    Py_BEGIN_ALLOW_THREADS
    error = sd_ble_write(address, uuid, data.buf, (size_t)data.len);
    Py_END_ALLOW_THREADS
    PyBuffer_Release(&data);
    return result_or_raise(error);
}

static PyMethodDef ble_methods[] = {
    {"scan", ble_scan, METH_VARARGS, "scan(timeout) -> JSON list of {name, address}"},
    {"connect", ble_connect, METH_VARARGS, "connect(address)"},
    {"disconnect", ble_disconnect, METH_VARARGS, "disconnect(address)"},
    {"subscribe", ble_subscribe, METH_VARARGS, "subscribe(address, uuid)"},
    {"write", ble_write, METH_VARARGS, "write(address, uuid, data)"},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef ble_module = {
    PyModuleDef_HEAD_INIT, "_sphero_ble", "CoreBluetooth, from the app's Swift code.", -1,
    ble_methods,
};

static PyObject *PyInit__sphero_ble(void) { return PyModule_Create(&ble_module); }

// --- starting Python, and Swift -> Python -------------------------------------

static char *copy_error(const char *prefix) {
    PyObject *type, *value, *tb;
    PyErr_Fetch(&type, &value, &tb);
    PyObject *s = value ? PyObject_Str(value) : NULL;
    const char *msg = s ? PyUnicode_AsUTF8(s) : "unknown error";
    size_t n = strlen(prefix) + strlen(msg) + 3;
    char *out = malloc(n);
    snprintf(out, n, "%s: %s", prefix, msg);
    Py_XDECREF(s);
    Py_XDECREF(type);
    Py_XDECREF(value);
    Py_XDECREF(tb);
    return out;
}

static char *status_error(PyStatus status) {
    const char *msg = status.err_msg ? status.err_msg : "unknown error";
    return strdup(msg);
}

char *sd_python_start(const char *home, const char *stdlib, const char *paths) {
    if (PyImport_AppendInittab("_sphero_ble", PyInit__sphero_ble) == -1) {
        return strdup("couldn't register _sphero_ble");
    }
    PyConfig config;
    PyConfig_InitIsolatedConfig(&config);
    config.buffered_stdio = 0;
    config.write_bytecode = 0;
    config.install_signal_handlers = 0;
    config.module_search_paths_set = 1;

    PyStatus status = PyConfig_SetBytesString(&config, &config.home, home);
    if (PyStatus_Exception(status)) goto fail;

    // The standard library, its binary modules, then the app's own directories.
    char buf[4096];
    const char *dirs[] = {"", "/lib-dynload"};
    for (int i = 0; i < 2; i++) {
        snprintf(buf, sizeof buf, "%s%s", stdlib, dirs[i]);
        wchar_t *w = Py_DecodeLocale(buf, NULL);
        status = PyWideStringList_Append(&config.module_search_paths, w);
        PyMem_RawFree(w);
        if (PyStatus_Exception(status)) goto fail;
    }
    for (const char *p = paths; *p; p += strlen(p) + 1) {
        wchar_t *w = Py_DecodeLocale(p, NULL);
        status = PyWideStringList_Append(&config.module_search_paths, w);
        PyMem_RawFree(w);
        if (PyStatus_Exception(status)) goto fail;
    }

    status = Py_InitializeFromConfig(&config);
    if (PyStatus_Exception(status)) goto fail;
    PyConfig_Clear(&config);

    // Install the Bluetooth bridge, then let other threads take the GIL.
    PyObject *mod = PyImport_ImportModule("sphero_dev.ios_bridge");
    if (mod == NULL) {
        char *err = copy_error("importing sphero_dev.ios_bridge");
        PyEval_SaveThread();
        return err;
    }
    Py_DECREF(mod);
    PyEval_SaveThread();
    return NULL;

fail:
    PyConfig_Clear(&config);
    return status_error(status);
}

char *sd_python_call(const char *function, const char *argument) {
    PyGILState_STATE gil = PyGILState_Ensure();
    char *out = NULL;
    PyObject *mod = PyImport_ImportModule("sphero_dev.app");
    PyObject *result = NULL;
    if (mod != NULL) {
        result = argument ? PyObject_CallMethod(mod, function, "s", argument)
                          : PyObject_CallMethod(mod, function, NULL);
        Py_DECREF(mod);
    }
    if (result != NULL && PyUnicode_Check(result)) {
        out = strdup(PyUnicode_AsUTF8(result));
    } else {
        // sphero_dev.app's functions catch their own errors, so this is a
        // missing module or function: report it as an error message.
        char *err = PyErr_Occurred() ? copy_error(function) : strdup("not a string");
        size_t n = strlen(err) + 96;
        out = malloc(n);
        snprintf(out, n,
                 "{\"messages\":[{\"role\":\"error\",\"parts\":[{\"type\":\"text\",\"text\":\"%s\"}]}]}",
                 "Python failed; see the Xcode console.");
        fprintf(stderr, "sd_python_call(%s): %s\n", function, err);
        free(err);
    }
    Py_XDECREF(result);
    PyGILState_Release(gil);
    return out;
}

void sd_python_notify(const char *address, const char *uuid, const uint8_t *data, size_t length) {
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject *mod = PyImport_ImportModule("sphero_dev.ios_adapter");
    if (mod != NULL) {
        PyObject *r = PyObject_CallMethod(mod, "on_notify", "ssy#", address, uuid,
                                          (const char *)data, (Py_ssize_t)length);
        if (r == NULL) PyErr_Print();
        Py_XDECREF(r);
        Py_DECREF(mod);
    } else {
        PyErr_Print();
    }
    PyGILState_Release(gil);
}
