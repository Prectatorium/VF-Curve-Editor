# VF Curve Editor

A Python tool for parsing, shifting, and optionally capping MSI Afterburner / NVIDIA VF (Voltage-Frequency) curve blobs.

## Overview

This tool manipulates the binary VF curve data used by MSI Afterburner and NVIDIA drivers. It allows you to shift the entire frequency curve, apply additional offsets, and cap frequencies above a specified voltage—all while preserving the original hardware reference frequencies.

## How It Works

The VF curve blob contains a sequence of P-state entries, each consisting of three IEEE-754 single-precision floats:

| Field | Description |
|-------|-------------|
| `volt` | Voltage for this P-state (mV) |
| `freq` | Hardware reference frequency (MHz) – never modified |
| `offset` | Runtime delta added to `freq` (MHz) |

**Effective frequency** = `freq + offset` – this is what Afterburner displays as the curve position.

## Blob Structure

```
[HEADER: 24 hex chars / 12 bytes] [N x ENTRY: 24 hex chars / 12 bytes each]
```

- Each entry is packed as three little-endian floats (`fff`)
- Entries with `volt == 0.0` and `freq == 0.0` are sentinels (end-of-data markers)

## Sanity Limits

| Field | Min | Max |
|-------|-----|-----|
| Voltage | 400 mV | 1250 mV |
| Frequency | 100 MHz | 3000 MHz |
| Offset | -500 MHz | +500 MHz |

## Installation

No installation required – the script is standalone. Just ensure you have Python 3.9+.

```bash
# Make executable
chmod +x vf_curve_editor.py

# Or run with python
python vf_curve_editor.py
```

## Usage Examples

```bash
# Use default file 'vf_curve_blob.txt' in current directory
python vf_curve_editor.py

# Shift the entire curve by 10 steps (look ahead 10 P-states)
python vf_curve_editor.py my_blob.txt -s 10

# Shift by 8 steps plus an extra 15 MHz
python vf_curve_editor.py my_blob.txt -s 8 -f 15

# Shift by 10 steps and cap all frequencies above 900 mV
python vf_curve_editor.py my_blob.txt -s 10 -c 900

# Validate a blob without modifying it
python vf_curve_editor.py my_blob.txt --validate

# Read blob from stdin
cat my_blob.txt | python vf_curve_editor.py - -s 5

# Save output to a file
python vf_curve_editor.py my_blob.txt -s 10 -o modified_blob.txt
```

## Command Line Options

| Option | Description |
|--------|-------------|
| `BLOB_FILE` | Path to blob file, `-` for stdin, or omit for `vf_curve_blob.txt` |
| `-s, --shift` | Look-ahead index shift (must be < number of VF entries) |
| `-f, --foffset` | Additional frequency offset (MHz) added on top of shift |
| `-c, --cutoff` | Lock frequencies for all entries at or above this voltage (mV) |
| `-o, --output` | Write result to file instead of stdout |
| `--validate` | Parse and validate blob without modifying |
| `-v, --verbose` | Enable debug logging |
| `--version` | Show version and exit |

## Shift Semantics

When shifting by `N` steps, each entry's effective frequency becomes:

```
new_effective_freq[i] = original_effective_freq[i + N] + freq_offset
new_offset[i] = new_effective_freq[i] - freq[i]
```

The original `freq` values remain unchanged – only `offset` is modified.

## Cutoff Semantics

When a cutoff voltage is specified:

1. The shifted effective frequency is computed for the last entry **below** the cutoff
2. Every entry at or above the cutoff voltage is locked to that same frequency

This creates a flat frequency response above the cutoff point.

## Output Format

The modified blob is printed to stdout (or a file) as a continuous hex string, preserving the original header and any trailing padding.

## Validation

The tool performs several validation checks:

- Hex string format and length
- Float decoding sanity
- Hardware range limits (voltage, frequency, offset)
- Non-finite value detection (NaN, Inf)

Use `--validate` to check blob integrity without making changes.

## Error Handling

| Error Type | Description |
|------------|-------------|
| `BlobError` | Hex format issues, unpacking failures, or sanity violations |
| `ValueError` | Invalid shift parameters (negative shift, shift ≥ entry count) |
| I/O errors | File not found, permission issues, etc. |

## Example Workflow

1. **Extract blob from Afterburner** (using a hex editor or memory scanner)
2. **Save to a text file** (e.g., `vf_curve_blob.txt`)
3. **Validate** the blob: `python vf_curve_editor.py --validate`
4. **Apply transformations**:
   ```bash
   python vf_curve_editor.py -s 8 -f 15 -c 950
   ```
5. **Copy output** back into Afterburner

## Notes

- Tested on GTX 10-series hardware
- The tool never modifies the original `freq` values – only `offset` is changed
- Sentinels (zero entries) are preserved exactly as in the original blob
- The header is left untouched

## License

Feel free to use, modify, and distribute as needed.
