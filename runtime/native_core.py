from __future__ import annotations

import ctypes
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional


ABI_VERSION = 1
FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211
VALID_MODES = {"python", "native", "dual"}
STATE_IDS = {
    "unknown": 0,
    "idle": 1,
    "queued": 2,
    "running": 3,
    "completed": 4,
    "interrupted": 5,
    "cancelled": 6,
    "error": 7,
    "budget_exhausted": 8,
}

_LOAD_LOCK = threading.Lock()
_PARITY_LOCK = threading.Lock()
_BINDINGS: Optional["_NativeBindings"] = None
_BINDINGS_PATH: Optional[Path] = None
_LOAD_ERROR: Optional[str] = None
_MODE_ENV: Optional[str] = None
_MODE_VALUE = "dual"
_LIBRARY_ENV: Optional[str] = None
_LIBRARY_PATH: Optional[Path] = None
_PARITY_CHECKS = 0
_PARITY_FAILURES = 0
_LAST_PYTHON_CLOCK = 0
_LAST_NATIVE_CLOCK = 0
_ALLOWED_TRANSITIONS = {
    0: frozenset({1, 2}),
    1: frozenset({2}),
    2: frozenset({3, 5, 6, 7}),
    3: frozenset({4, 5, 6, 7, 8}),
    5: frozenset({2, 3, 6, 7}),
}


class NativeCoreError(RuntimeError):
    pass


class NativeParityError(NativeCoreError):
    pass


class _NativeBindings:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.library = ctypes.CDLL(str(path))
        self.library.para_core_abi_version.argtypes = []
        self.library.para_core_abi_version.restype = ctypes.c_uint32
        self.library.para_monotonic_ns.argtypes = []
        self.library.para_monotonic_ns.restype = ctypes.c_uint64
        self.library.para_fnv1a64.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        self.library.para_fnv1a64.restype = ctypes.c_uint64
        self.library.para_transition_allowed.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        self.library.para_transition_allowed.restype = ctypes.c_int32
        self.library.para_json_escape.argtypes = [
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_void_p,
            ctypes.c_size_t,
        ]
        self.library.para_json_escape.restype = ctypes.c_size_t
        self.library.para_append_line_utf8.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t]
        self.library.para_append_line_utf8.restype = ctypes.c_int32
        actual_abi = int(self.library.para_core_abi_version())
        if actual_abi != ABI_VERSION:
            raise NativeCoreError(f"Native ABI mismatch: expected {ABI_VERSION}, received {actual_abi}.")

    @staticmethod
    def _buffer(payload: bytes) -> tuple[Optional[ctypes.Array[Any]], Optional[ctypes.c_void_p]]:
        if not payload:
            return None, None
        buffer = ctypes.create_string_buffer(payload, len(payload))
        return buffer, ctypes.cast(buffer, ctypes.c_void_p)

    def monotonic_ns(self) -> int:
        value = int(self.library.para_monotonic_ns())
        if value <= 0:
            raise NativeCoreError("Native monotonic clock returned an invalid value.")
        return value

    def fnv1a64(self, payload: bytes) -> int:
        buffer, pointer = self._buffer(payload)
        _ = buffer
        return int(self.library.para_fnv1a64(pointer, len(payload)))

    def transition_allowed(self, from_state: int, to_state: int) -> bool:
        return bool(self.library.para_transition_allowed(from_state, to_state))

    def json_escape(self, value: str) -> str:
        payload = value.encode("utf-8")
        source, pointer = self._buffer(payload)
        _ = source
        required = int(self.library.para_json_escape(pointer, len(payload), None, 0))
        if required == ctypes.c_size_t(-1).value:
            raise NativeCoreError("Native JSON escape rejected its input.")
        output = ctypes.create_string_buffer(required + 1)
        written = int(
            self.library.para_json_escape(
                pointer,
                len(payload),
                ctypes.cast(output, ctypes.c_void_p),
                len(output),
            )
        )
        if written != required:
            raise NativeCoreError(f"Native JSON escape length mismatch: expected {required}, wrote {written}.")
        return bytes(output.raw[:written]).decode("utf-8")

    def append_line(self, path: Path, line: str) -> None:
        path_bytes = str(path).encode("utf-8")
        payload = line.encode("utf-8")
        buffer, pointer = self._buffer(payload)
        _ = buffer
        result = int(self.library.para_append_line_utf8(path_bytes, pointer, len(payload)))
        if result != 0:
            raise NativeCoreError(f"Native append failed with code {result} for {path}.")


def requested_mode() -> str:
    global _MODE_ENV, _MODE_VALUE
    raw = str(os.getenv("PARALLM_CORE_MODE") or "dual")
    if raw == _MODE_ENV:
        return _MODE_VALUE
    value = raw.strip().lower()
    _MODE_ENV = raw
    _MODE_VALUE = value if value in VALID_MODES else "dual"
    return _MODE_VALUE


def library_path() -> Path:
    global _LIBRARY_ENV, _LIBRARY_PATH
    raw = str(os.getenv("PARALLM_NATIVE_CORE_LIBRARY") or "")
    if raw == _LIBRARY_ENV and _LIBRARY_PATH is not None:
        return _LIBRARY_PATH
    override = raw.strip()
    if override:
        resolved = Path(override).expanduser().resolve()
    else:
        root = Path(__file__).resolve().parents[1]
        build_dir = root / "native" / "build"
        manifest_path = build_dir / "manifest.json"
        resolved = None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
            library = artifacts.get("library") if isinstance(artifacts.get("library"), dict) else {}
            candidate = (root / str(library.get("path") or "")).resolve()
            if candidate.is_relative_to(build_dir.resolve()) and candidate.is_file():
                resolved = candidate
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            resolved = None
        if resolved is None:
            if os.name == "nt":
                filename = "paracore.dll"
            elif os.uname().sysname.lower() == "darwin":
                filename = "libparacore.dylib"
            else:
                filename = "libparacore.so"
            resolved = build_dir / filename
    _LIBRARY_ENV = raw
    _LIBRARY_PATH = resolved
    return resolved


def _load_bindings() -> Optional[_NativeBindings]:
    global _BINDINGS, _BINDINGS_PATH, _LOAD_ERROR
    path = library_path()
    if _BINDINGS is not None and _BINDINGS_PATH == path:
        return _BINDINGS
    if _BINDINGS_PATH == path and _LOAD_ERROR is not None:
        return None
    with _LOAD_LOCK:
        if _BINDINGS is not None and _BINDINGS_PATH == path:
            return _BINDINGS
        if _BINDINGS_PATH == path and _LOAD_ERROR is not None:
            return None
        _BINDINGS = None
        _BINDINGS_PATH = path
        _LOAD_ERROR = None
        try:
            if not path.is_file():
                raise NativeCoreError(f"Native core library not found at {path}.")
            _BINDINGS = _NativeBindings(path)
        except Exception as error:
            _LOAD_ERROR = str(error)
        return _BINDINGS


def _required_bindings() -> _NativeBindings:
    bindings = _load_bindings()
    if bindings is None:
        raise NativeCoreError(_LOAD_ERROR or "Native core is unavailable.")
    return bindings


def effective_mode() -> str:
    mode = requested_mode()
    if mode == "python":
        return "python"
    if _load_bindings() is None:
        if mode == "native":
            _required_bindings()
        return "python"
    return mode


def _record_parity(matches: bool, operation: str) -> None:
    global _PARITY_CHECKS, _PARITY_FAILURES
    with _PARITY_LOCK:
        _PARITY_CHECKS += 1
        if not matches:
            _PARITY_FAILURES += 1
    if not matches:
        raise NativeParityError(f"Python/native parity failed for {operation}.")


def _python_fnv1a64(payload: bytes) -> int:
    value = FNV_OFFSET
    for byte in payload:
        value ^= byte
        value = (value * FNV_PRIME) & 0xFFFFFFFFFFFFFFFF
    return value


def fnv1a64(value: str | bytes) -> int:
    payload = value.encode("utf-8") if isinstance(value, str) else bytes(value)
    python_value = _python_fnv1a64(payload)
    mode = effective_mode()
    if mode == "python":
        return python_value
    native_value = _required_bindings().fnv1a64(payload)
    if mode == "dual":
        _record_parity(native_value == python_value, "fnv1a64")
        return python_value
    return native_value


def fnv1a64_hex(value: str | bytes) -> str:
    return f"{fnv1a64(value):016x}"


def _python_transition_allowed(from_state: str, to_state: str) -> bool:
    source = STATE_IDS.get(str(from_state or "").strip().lower(), 0)
    target = STATE_IDS.get(str(to_state or "").strip().lower(), 0)
    if source == target:
        return True
    return target in _ALLOWED_TRANSITIONS.get(source, frozenset())


def transition_allowed(from_state: str, to_state: str) -> bool:
    source = STATE_IDS.get(str(from_state or "").strip().lower(), 0)
    target = STATE_IDS.get(str(to_state or "").strip().lower(), 0)
    python_value = _python_transition_allowed(from_state, to_state)
    mode = effective_mode()
    if mode == "python":
        return python_value
    native_value = _required_bindings().transition_allowed(source, target)
    if mode == "dual":
        _record_parity(native_value == python_value, "transition_allowed")
        return python_value
    return native_value


def _python_json_escape(value: str) -> str:
    encoded = json.dumps(str(value), ensure_ascii=False, separators=(",", ":"))
    return encoded[1:-1]


def json_escape(value: str) -> str:
    python_value = _python_json_escape(value)
    mode = effective_mode()
    if mode == "python":
        return python_value
    native_value = _required_bindings().json_escape(str(value))
    if mode == "dual":
        _record_parity(native_value == python_value, "json_escape")
        return python_value
    return native_value


def monotonic_ns() -> int:
    global _LAST_NATIVE_CLOCK, _LAST_PYTHON_CLOCK
    python_value = time.perf_counter_ns()
    mode = effective_mode()
    if mode == "python":
        return python_value
    native_value = _required_bindings().monotonic_ns()
    if mode == "dual":
        with _PARITY_LOCK:
            clocks_valid = python_value >= _LAST_PYTHON_CLOCK and native_value >= _LAST_NATIVE_CLOCK
            _LAST_PYTHON_CLOCK = python_value
            _LAST_NATIVE_CLOCK = native_value
        _record_parity(clocks_valid, "monotonic_ns")
        return python_value
    return native_value


def append_line(path: str | Path, line: str) -> None:
    target = Path(path)
    mode = effective_mode()
    if mode == "native":
        _required_bindings().append_line(target, line)
        return
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.write("\n")


def status() -> Dict[str, Any]:
    mode = requested_mode()
    bindings = None if mode == "python" else _load_bindings()
    with _PARITY_LOCK:
        checks = _PARITY_CHECKS
        failures = _PARITY_FAILURES
    return {
        "abiVersion": ABI_VERSION,
        "requestedMode": mode,
        "effectiveMode": "python" if mode != "python" and bindings is None else mode,
        "nativeAvailable": bindings is not None,
        "libraryPath": str(library_path()),
        "loadError": _LOAD_ERROR,
        "parityChecks": checks,
        "parityFailures": failures,
        "ready": mode != "native" or bindings is not None,
    }


def reset_for_tests() -> None:
    global _BINDINGS, _BINDINGS_PATH, _LOAD_ERROR
    global _MODE_ENV, _MODE_VALUE, _LIBRARY_ENV, _LIBRARY_PATH
    global _PARITY_CHECKS, _PARITY_FAILURES, _LAST_PYTHON_CLOCK, _LAST_NATIVE_CLOCK
    with _LOAD_LOCK:
        _BINDINGS = None
        _BINDINGS_PATH = None
        _LOAD_ERROR = None
        _MODE_ENV = None
        _MODE_VALUE = "dual"
        _LIBRARY_ENV = None
        _LIBRARY_PATH = None
    with _PARITY_LOCK:
        _PARITY_CHECKS = 0
        _PARITY_FAILURES = 0
        _LAST_PYTHON_CLOCK = 0
        _LAST_NATIVE_CLOCK = 0
