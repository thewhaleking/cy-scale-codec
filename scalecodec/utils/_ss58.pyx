# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True, nonecheck=False

"""Fast Cython implementations of base58 / SS58 encoding for the AccountId
hot path.

`base58.b58encode_int` from the upstream `base58` package is O(N²) in the
output digit count due to repeated bytes-prepending. `b58encode_bytes` here
runs the standard base-256 → base-58 byte-array divmod algorithm directly on
a C buffer, then emits ASCII output in one pass — no Python big-int divmod,
no quadratic concatenation.

`ss58_encode_fast` inlines the prefix-byte construction, blake2b checksum,
and base58 encode that `scalecodec.utils.ss58.ss58_encode` performs, so the
whole SS58 encode of an AccountId costs one Python frame instead of ~6.
"""

from cpython.bytes cimport PyBytes_FromStringAndSize, PyBytes_AsString
from libc.stdint cimport uint32_t

from hashlib import blake2b


# Bitcoin base58 alphabet — the only alphabet SS58 uses. Kept as a module-level
# bytes object so the `_ALPHA` pointer stays valid for the module's lifetime.
cdef bytes _ALPHABET_BYTES = b'123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
cdef unsigned char* _ALPHA = <unsigned char*>PyBytes_AsString(_ALPHABET_BYTES)

# Inverse table: ASCII byte → base-58 digit (0..57), 0xFF for invalid chars.
cdef unsigned char _ALPHA_INV[256]

cdef _init_inverse_alphabet():
    cdef int i
    for i in range(256):
        _ALPHA_INV[i] = 0xFF
    for i in range(58):
        _ALPHA_INV[_ALPHA[i]] = <unsigned char>i

_init_inverse_alphabet()

cdef bytes _SS58PRE = b"SS58PRE"


cpdef bytes b58encode_bytes(const unsigned char[:] data):
    """Base58-encode a byte buffer (Bitcoin alphabet).

    Equivalent to ``bytes(base58.b58encode(bytes(data)))`` but operates
    entirely on fixed-size byte buffers.
    """
    cdef Py_ssize_t n = data.shape[0]
    if n == 0:
        return b""

    # Each leading zero byte becomes a leading '1' in base58.
    cdef Py_ssize_t leading_zeros = 0
    while leading_zeros < n and data[leading_zeros] == 0:
        leading_zeros += 1

    # log2(256) / log2(58) ≈ 1.3661 — 138/100 is the standard safe bound.
    cdef Py_ssize_t cap = (n - leading_zeros) * 138 // 100 + 1
    cdef bytearray digits_ba = bytearray(cap)
    cdef unsigned char[:] digits = digits_ba
    cdef Py_ssize_t digit_count = 0

    cdef Py_ssize_t i, j
    cdef uint32_t carry

    for i in range(leading_zeros, n):
        carry = data[i]
        j = 0
        # Multiply existing base-58 digits by 256, then add the new byte.
        while j < digit_count or carry > 0:
            if j < digit_count:
                carry += <uint32_t>digits[j] * <uint32_t>256
            digits[j] = <unsigned char>(carry % <uint32_t>58)
            carry //= <uint32_t>58
            j += 1
        digit_count = j

    cdef Py_ssize_t out_len = leading_zeros + digit_count
    cdef bytes out = PyBytes_FromStringAndSize(NULL, out_len)
    cdef unsigned char* out_buf = <unsigned char*>PyBytes_AsString(out)

    for i in range(leading_zeros):
        out_buf[i] = _ALPHA[0]
    for i in range(digit_count):
        out_buf[leading_zeros + i] = _ALPHA[digits[digit_count - 1 - i]]

    return out


cpdef bytes b58decode_bytes(object data):
    """Base58-decode an ASCII input (str or bytes-like) to raw bytes.

    Equivalent to ``base58.b58decode(data)`` for the Bitcoin alphabet. Raises
    ``ValueError`` on characters outside the alphabet.
    """
    cdef bytes ascii_bytes
    if isinstance(data, str):
        ascii_bytes = data.rstrip().encode("ascii")
    elif isinstance(data, (bytes, bytearray, memoryview)):
        ascii_bytes = bytes(data).rstrip()
    else:
        raise TypeError("b58decode_bytes: expected str or bytes-like")

    cdef Py_ssize_t n = len(ascii_bytes)
    if n == 0:
        return b""

    cdef const unsigned char* in_buf = <const unsigned char*>PyBytes_AsString(ascii_bytes)

    # Leading '1' chars map to leading zero bytes in the output.
    cdef Py_ssize_t leading_ones = 0
    while leading_ones < n and in_buf[leading_ones] == _ALPHA[0]:
        leading_ones += 1

    # log2(58) / log2(256) ≈ 0.7322; 733/1000 is the standard safe bound.
    cdef Py_ssize_t cap = (n - leading_ones) * 733 // 1000 + 1
    cdef bytearray buf_ba = bytearray(cap)
    cdef unsigned char[:] buf = buf_ba
    cdef Py_ssize_t length = 0

    cdef Py_ssize_t i, j
    cdef uint32_t carry
    cdef unsigned char digit

    for i in range(leading_ones, n):
        digit = _ALPHA_INV[in_buf[i]]
        if digit == 0xFF:
            raise ValueError(f"Invalid character {chr(in_buf[i])!r}")
        carry = digit
        j = 0
        while j < length or carry > 0:
            if j < length:
                carry += <uint32_t>buf[j] * <uint32_t>58
            buf[j] = <unsigned char>(carry & 0xFF)
            carry >>= 8
            j += 1
        length = j

    cdef Py_ssize_t out_len = leading_ones + length
    cdef bytes out = PyBytes_FromStringAndSize(NULL, out_len)
    cdef unsigned char* out_buf = <unsigned char*>PyBytes_AsString(out)

    for i in range(leading_ones):
        out_buf[i] = 0
    for i in range(length):
        out_buf[leading_ones + i] = buf[length - 1 - i]

    return out


cpdef str ss58_encode_fast(object address, int ss58_format=42):
    """Encode an account ID (or account index bytes) as an SS58 address.

    Mirrors ``scalecodec.utils.ss58.ss58_encode`` in behavior; differs only
    in that the prefix-byte construction, blake2b checksum, and base58
    encoding happen in this single Cython entry point.
    """
    if ss58_format < 0 or ss58_format > 16383 or ss58_format == 46 or ss58_format == 47:
        raise ValueError("Invalid value for ss58_format")

    cdef bytes address_bytes
    if isinstance(address, bytes):
        address_bytes = address
    elif isinstance(address, bytearray):
        address_bytes = bytes(address)
    elif isinstance(address, str):
        if address.startswith("0x"):
            address_bytes = bytes.fromhex(address[2:])
        else:
            address_bytes = bytes.fromhex(address)
    else:
        raise TypeError("address must be bytes, bytearray, or hex str")

    cdef Py_ssize_t addr_len = len(address_bytes)
    cdef int checksum_length
    if addr_len == 32 or addr_len == 33:
        checksum_length = 2
    elif addr_len == 1 or addr_len == 2 or addr_len == 4 or addr_len == 8:
        checksum_length = 1
    else:
        raise ValueError("Invalid length for address")

    cdef bytes prefix_bytes
    if ss58_format < 64:
        prefix_bytes = bytes([ss58_format])
    else:
        prefix_bytes = bytes([
            ((ss58_format & 0x00FC) >> 2) | 0x40,
            (ss58_format >> 8) | ((ss58_format & 0x0003) << 6),
        ])

    cdef bytes input_bytes = prefix_bytes + address_bytes
    cdef bytes checksum = blake2b(_SS58PRE + input_bytes).digest()
    cdef bytes payload = input_bytes + checksum[:checksum_length]
    return b58encode_bytes(payload).decode("ascii")