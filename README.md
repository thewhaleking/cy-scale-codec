# cyscale

[![Latest Version](https://img.shields.io/pypi/v/cyscale.svg)](https://pypi.org/project/cyscale/)
[![Supported Python versions](https://img.shields.io/pypi/pyversions/cyscale.svg)](https://pypi.org/project/cyscale/)
[![License](https://img.shields.io/pypi/l/cyscale.svg)](https://github.com/thewhaleking/cy-scale-codec/blob/master/LICENSE)

Cython-accelerated [SCALE codec](https://docs.substrate.io/reference/scale-codec/) library for Substrate-based blockchains (Polkadot, Kusama, Bittensor, etc.).

A drop-in replacement for [py-scale-codec](https://github.com/polkascan/py-scale-codec) — same `scalecodec` module name, same public API, compiled with Cython for improved throughput.

## Installation

```bash
pip install cyscale
```

## Performance

Benchmarked on Apple M-series (Python 3.13) against py-scale-codec 1.2.12.
All timings are µs per call; speedup = py ÷ cy.

### Primitives and small types

| Benchmark                   | py (µs) | cy (µs) | speedup |
|-----------------------------|---------|---------|---------|
| u8 decode                   | 2.18    | 1.29    | 1.68×   |
| u16 decode                  | 2.12    | 1.40    | 1.52×   |
| u32 decode                  | 2.10    | 1.37    | 1.53×   |
| u64 decode                  | 2.14    | 1.39    | 1.54×   |
| u128 decode                 | 2.11    | 1.37    | 1.53×   |
| Compact\<u32\> decode       | 6.94    | 4.94    | 1.40×   |
| bool decode                 | 2.10    | 1.33    | 1.58×   |
| H256 decode                 | 2.14    | 1.37    | 1.57×   |
| AccountId decode (SS58 format 42)  | 8.91    | 8.84    | 1.01×   |
| Str decode                  | 9.20    | 6.37    | 1.44×   |
| (u32, u64, bool) decode     | 16.11   | 10.69   | 1.51×   |
| u32 encode                  | 1.65    | 0.98    | 1.68×   |
| u64 encode                  | 1.68    | 0.98    | 1.71×   |
| Compact\<u32\> encode       | 6.47    | 4.53    | 1.43×   |
| H256 encode                 | 1.77    | 1.04    | 1.70×   |

### Large payloads

| Benchmark                                       | py (µs)    | cy (µs)    | speedup |
|-------------------------------------------------|------------|------------|---------|
| Vec\<u32\> decode (64 elements)                 | 160.57     | 105.46     | 1.52×   |
| Vec\<u32\> decode (1,024 elements)              | 2,329.76   | 1,574.94   | 1.48×   |
| Vec\<u32\> decode (16,384 elements)             | 37,470.39  | 24,791.11  | 1.51×   |
| Bytes decode (1 KB)                             | 10.35      | 7.65       | 1.35×   |
| Bytes decode (64 KB)                            | 46.01      | 45.50      | 1.01×   |
| Bytes decode (512 KB)                           | 270.51     | 290.45     | 0.93×   |
| Vec\<EventRecord\> decode (5 events, V10)       | 215.79     | 145.50     | 1.48×   |
| MetadataVersioned decode (V10, 85 KB)           | 47,144.57  | 33,035.40  | 1.43×   |
| MetadataVersioned decode (V13, 219 KB)          | 102,974.25 | 73,624.13  | 1.40×   |
| MetadataVersioned decode (V14, 300 KB)          | 284,478.38 | 199,015.58 | 1.43×   |
| Bittensor metadata + portable registry (254 KB) | 332,447.63 | 229,223.60 | 1.45×   |

Primitives and small types see **~1.4–1.7× speedup**. Large metadata decoding
sees **~1.4–1.5× speedup** — the gain compounds across thousands of recursive
decode calls. Raw bulk byte operations (`Bytes`/`Vec<u8>`) above ~64 KB are
dominated by `memcpy` and show no meaningful difference.

`AccountId` with SS58 encoding shows ~1× speedup because the cost is dominated
by the Python `ss58_encode` call, not the SCALE decode itself.

### batch_decode (cyscale-only API)

`batch_decode(type_strings, bytes_list)` amortises Python dispatch overhead
across a list of decodes. For uniform `AccountId` workloads, gains are modest
(SS58 dominates); for mixed-type batches the dispatch savings become visible.
Note: `bt_decode` is excluded from this comparison because it does not perform
SS58 encoding — including it without that post-processing step would be an
unfair comparison.

| Benchmark                                       | batch (µs) | loop (µs) | speedup |
|-------------------------------------------------|------------|-----------|---------|
| AccountId ×10                                   | 87.3       | 92.1      | 1.06×   |
| AccountId ×100                                  | 870.1      | 897.6     | 1.03×   |
| AccountId ×1,000                                | 8693.5     | 8954.4    | 1.03×   |
| Mixed (AccountId / u32 / u128) ×100             | 303.9      | 444.5     | 1.46×   |

To reproduce, run:

```bash
# save a py-scale-codec baseline
python benchmarks/bench.py --save-baseline benchmarks/baseline_py.json

# compare against cy-scale-codec
PYTHONPATH=. python benchmarks/bench.py --compare benchmarks/baseline_py.json
```

## Examples of different types

| Type | Description | Example SCALE decoding value | SCALE encoded value |
|------|-------------|------------------------------|---------------------|
| `bool` | Boolean values are encoded using the least significant bit of a single byte. | `True` | `0x01` |
| `u16` | Basic integers are encoded using a fixed-width little-endian (LE) format. | `42` | `0x2a00` |
| `Compact` | A "compact" or general integer encoding is sufficient for encoding large integers (up to 2\*\*536) and is more efficient at encoding most values than the fixed-width version. | `1` | `0x04` |
| `Vec` | A collection of same-typed values is encoded, prefixed with a compact encoding of the number of items, followed by each item's encoding concatenated in turn. | `[4, 8, 15, 16, 23, 42]` | `0x18040008000f00100017002a00` |
| `str`, `Bytes` | Strings are Vectors of bytes (`Vec<u8>`) containing a valid UTF8 sequence. | `"Test"` | `0x1054657374` |
| `AccountId` | An [SS58 formatted](https://docs.substrate.io/reference/address-formats/) representation of an account. | `"5GDyPHLVHcQYPTWfygtPYeogQjyZy7J9fsi4brPhgEFq4pcv"` | `0xb80269ec...` |
| `Enum` | A fixed number of variants, each mutually exclusive. Encoded as the first byte identifying the index of the variant. | `{'Int': 8}` | `0x002a` |
| `Struct` | For structures, values are named but that is irrelevant for the encoding (only order matters). | `{"votes": [...], "id": 4}` | `0x04b80269...` |

## License

Apache 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
