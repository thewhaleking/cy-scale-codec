"""Some simple math-related utility functions not present in the standard
library.
"""

from decimal import Decimal
from math import ceil, log2
from typing import Union

_FixedInput = Union[int, dict]


def _extract_bits(value: _FixedInput) -> int:
    if isinstance(value, dict):
        return int(value["bits"])
    return int(value)


def fixed_to_float(value: _FixedInput, frac_bits: int = 64) -> float:
    """Decode a binary fixed-point value (Q notation) to a Python float.

    The default ``frac_bits=64`` corresponds to ``U64F64`` / ``I64F64``
    (a 128-bit value with 64 integer bits and 64 fractional bits), which is
    the most common fixed-point type in Substrate / Bittensor chains.

    Parameters
    ----------
    value:
        Either the raw integer bits, or the dict produced by the SCALE
        decoder (e.g. ``{'bits': 1489050730165858261}``).
    frac_bits:
        Number of fractional bits.  Common values:
        ``64`` for U64F64 / I64F64 (default),
        ``32`` for U32F32 / I32F32.

    Returns
    -------
    float
    """
    bits = _extract_bits(value)
    frac_mask = (1 << frac_bits) - 1
    integer_part = bits >> frac_bits
    fractional_part = bits & frac_mask
    return integer_part + fractional_part / (1 << frac_bits)


def fixed_to_decimal(value: _FixedInput, frac_bits: int = 64) -> Decimal:
    """Decode a binary fixed-point value (Q notation) to a ``decimal.Decimal``.

    Prefer this over :func:`fixed_to_float` when precision matters (e.g.
    token amounts, prices), since ``float`` cannot represent most fractional
    values exactly.

    Parameters
    ----------
    value:
        Either the raw integer bits, or the dict produced by the SCALE
        decoder (e.g. ``{'bits': 1489050730165858261}``).
    frac_bits:
        Number of fractional bits.  Defaults to ``64`` (U64F64 / I64F64).

    Returns
    -------
    decimal.Decimal
    """
    bits = _extract_bits(value)
    frac_mask = (1 << frac_bits) - 1
    integer_part = bits >> frac_bits
    fractional_part = bits & frac_mask
    return Decimal(integer_part) + Decimal(fractional_part) / Decimal(1 << frac_bits)


def trailing_zeros(value: int) -> int:
    """Returns the number of trailing zeros in the binary representation of
    the given integer.
    """
    num_zeros = 0
    while value & 1 == 0:
        num_zeros += 1
        value >>= 1
    return num_zeros


def next_power_of_two(value: int) -> int:
    """Returns the smallest power of two that is greater than or equal
    to the given integer.
    """
    if value < 0:
        raise ValueError("Negative integers not supported")
    return 1 if value == 0 else 1 << ceil(log2(value))
