import ctypes
from ctypes import wintypes

_crypt32 = ctypes.windll.crypt32
_kernel32 = ctypes.windll.kernel32

CRYPTPROTECT_UI_FORBIDDEN = 0x01


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


# --- argtypes / restype setup ---

_crypt32.CryptProtectData.argtypes = [
    ctypes.POINTER(DATA_BLOB),   # pDataIn
    wintypes.LPCWSTR,            # szDataDescr
    ctypes.POINTER(DATA_BLOB),   # pOptionalEntropy
    ctypes.c_void_p,             # pvReserved
    ctypes.c_void_p,             # pPromptStruct
    wintypes.DWORD,              # dwFlags
    ctypes.POINTER(DATA_BLOB),   # pDataOut
]
_crypt32.CryptProtectData.restype = wintypes.BOOL

_crypt32.CryptUnprotectData.argtypes = [
    ctypes.POINTER(DATA_BLOB),   # pDataIn
    ctypes.POINTER(wintypes.LPWSTR),  # ppszDataDescr (may be NULL)
    ctypes.POINTER(DATA_BLOB),   # pOptionalEntropy
    ctypes.c_void_p,             # pvReserved
    ctypes.c_void_p,             # pPromptStruct
    wintypes.DWORD,              # dwFlags
    ctypes.POINTER(DATA_BLOB),   # pDataOut
]
_crypt32.CryptUnprotectData.restype = wintypes.BOOL

_kernel32.LocalFree.argtypes = [ctypes.c_void_p]
_kernel32.LocalFree.restype = ctypes.c_void_p


def encrypt(plaintext: str) -> bytes:
    raw = plaintext.encode("utf-16-le")
    in_buf = (ctypes.c_byte * len(raw))(*raw)
    blob_in = DATA_BLOB(cbData=len(raw), pbData=in_buf)
    blob_out = DATA_BLOB()

    ok = _crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise RuntimeError(
            f"CryptProtectData failed (error {_kernel32.GetLastError()})"
        )

    try:
        return bytes(ctypes.string_at(blob_out.pbData, blob_out.cbData))
    finally:
        _kernel32.LocalFree(blob_out.pbData)


def decrypt(ciphertext: bytes) -> str:
    in_buf = (ctypes.c_byte * len(ciphertext))(*ciphertext)
    blob_in = DATA_BLOB(cbData=len(ciphertext), pbData=in_buf)
    blob_out = DATA_BLOB()
    desc_ptr = wintypes.LPWSTR(None)

    ok = _crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        ctypes.byref(desc_ptr),
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise RuntimeError(
            f"CryptUnprotectData failed (error {_kernel32.GetLastError()})"
        )

    try:
        raw = bytes(ctypes.string_at(blob_out.pbData, blob_out.cbData))
        return raw.decode("utf-16-le")
    finally:
        _kernel32.LocalFree(blob_out.pbData)
        # desc_ptr may be NULL if no description was stored; LocalFree handles NULL safely
        _kernel32.LocalFree(desc_ptr)
