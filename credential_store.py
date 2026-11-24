"""Persist the last API credentials, encrypted for the current Windows user.

Only the caller-selected file is used. Values are never logged, and no plaintext
fallback is used on platforms without Windows DPAPI.
"""

from contextlib import contextmanager
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import tempfile
import threading


class CredentialStoreError(Exception):
    """A credential operation failed without exposing credential contents."""


_PATH_LOCKS = {}
_PATH_LOCKS_GUARD = threading.Lock()


def _empty_credentials():
    return {"api_key": "", "law_oc": ""}


def _path_lock(path):
    key = os.path.normcase(str(path.resolve()))
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


def _crypt(data, *, decrypt=False):
    if os.name != "nt":
        raise CredentialStoreError("API 키 저장은 Windows에서만 지원됩니다.")

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = DataBlob(len(data), buffer)
    result = DataBlob()
    if decrypt:
        operation = crypt32.CryptUnprotectData
        operation.argtypes = [
            ctypes.POINTER(DataBlob), ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p,
            wintypes.DWORD, ctypes.POINTER(DataBlob),
        ]
    else:
        operation = crypt32.CryptProtectData
        operation.argtypes = [
            ctypes.POINTER(DataBlob), wintypes.LPCWSTR,
            ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p,
            wintypes.DWORD, ctypes.POINTER(DataBlob),
        ]
    operation.restype = wintypes.BOOL
    # CRYPTPROTECT_UI_FORBIDDEN; omitting LOCAL_MACHINE scopes DPAPI to this user.
    succeeded = operation(
        ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(result)
    )
    if not succeeded:
        raise CredentialStoreError("저장된 API 키를 암호화 또는 복호화할 수 없습니다.")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(result.pbData, ctypes.c_void_p))


class CredentialStore:
    def __init__(self, path):
        self.path = Path(path)
        self._thread_lock = _path_lock(self.path)

    @contextmanager
    def _locked(self):
        with self._thread_lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Use a separate persistent lock file because the data file is replaced.
            lock_path = self.path.with_name(self.path.name + ".lock")
            with lock_path.open("a+b") as lock_file:
                lock_file.seek(0, os.SEEK_END)
                if lock_file.tell() == 0:
                    lock_file.write(b"\0")
                    lock_file.flush()
                lock_file.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                    try:
                        yield
                    finally:
                        lock_file.seek(0)
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                    try:
                        yield
                    finally:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def load(self):
        """Return both values, or empty values if no credentials were saved."""
        try:
            with self._locked():
                if not self.path.exists():
                    return _empty_credentials()
                envelope = json.loads(self.path.read_text(encoding="utf-8"))
                if (not isinstance(envelope, dict)
                        or envelope.get("version") != 1
                        or envelope.get("encryption") != "windows-dpapi"
                        or not isinstance(envelope.get("ciphertext"), str)):
                    raise ValueError("Invalid credential format")
                encrypted = base64.b64decode(envelope["ciphertext"], validate=True)
                if not encrypted:
                    raise ValueError("Empty ciphertext")
                payload = json.loads(_crypt(encrypted, decrypt=True).decode("utf-8"))
                if (not isinstance(payload, dict)
                        or set(payload) != {"api_key", "law_oc"}
                        or not all(isinstance(value, str) for value in payload.values())):
                    raise ValueError("Invalid credential payload")
                return {key: value.strip() for key, value in payload.items()}
        except Exception:
            raise CredentialStoreError("저장된 API 키를 읽을 수 없습니다.") from None

    def save(self, api_key, law_oc):
        """Replace both saved values; empty strings clear the respective value."""
        temporary_path = None
        try:
            if not isinstance(api_key, str) or not isinstance(law_oc, str):
                raise ValueError("Credentials must be strings")
            payload = {"api_key": api_key.strip(), "law_oc": law_oc.strip()}
            encrypted = _crypt(
                json.dumps(payload, ensure_ascii=False).encode("utf-8")
            )
            envelope = {
                "version": 1,
                "encryption": "windows-dpapi",
                "ciphertext": base64.b64encode(encrypted).decode("ascii"),
            }
            with self._locked():
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=self.path.parent,
                    prefix="." + self.path.name + ".", suffix=".tmp", delete=False,
                ) as temporary_file:
                    temporary_path = Path(temporary_file.name)
                    json.dump(envelope, temporary_file, ensure_ascii=True)
                    temporary_file.flush()
                    os.fsync(temporary_file.fileno())
                os.replace(temporary_path, self.path)
                temporary_path = None
        except Exception:
            raise CredentialStoreError("API 키를 저장할 수 없습니다.") from None
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
