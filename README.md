# VF Curve Editor

A Python tool for parsing, shifting, and modifying MSI Afterburner voltage-frequency (VF) curve blobs for NVIDIA GPUs.

## Overview

This tool allows you to programmatically edit the VF curve blobs used by MSI Afterburner to store GPU voltage-frequency profiles. It's particularly useful for:

- Applying systematic frequency shifts across the entire VF curve
- Capping frequencies above a certain voltage threshold
- Batch-processing curve adjustments without manual GUI interaction

The tool has been **tested on RTX 30-series and GTX 10-series** GPUs.

## How It Works

MSI Afterburner stores VF curve data in configuration files as hexadecimal blobs. Each blob contains:

- A 12-byte (24 hex char) header
- A series of 12-byte (24 hex char) entries, each containing three IEEE-754 single-precision floats:
  - **Voltage** (mV) - The voltage point for this P-state
  - **Frequency** (MHz) - Hardware reference frequency (never modified)
  - **Offset** (MHz) - Delta added to frequency at runtime (effective = freq + offset)

Entries with `volt == 0.0` and `freq == 0.0` act as sentinels marking the end of valid data.

## Installation

No installation required - just save the script and ensure you have Python 3.9+:

```bash
# Make the script executable (Linux/Mac)
chmod +x vf_curve_editor.py

# Or run directly with Python
python vf_curve_editor.py
```

## Usage

### Basic Commands

```bash
# Use default blob file (vf_curve_blob.txt in current directory)
python vf_curve_editor.py

# Shift the curve by 10 steps (look ahead 10 P-states)
python vf_curve_editor.py my_blob.txt -s 10

# Shift by 8 steps and add 15 MHz extra offset
python vf_curve_editor.py my_blob.txt -s 8 -f 15

# Shift by 10 steps and cap all points above 900 mV
python vf_curve_editor.py my_blob.txt -s 10 -c 900

# Validate a blob without modifying it
python vf_curve_editor.py my_blob.txt --validate

# Read from stdin and write to file
cat blob.txt | python vf_curve_editor.py - -s 5 -o modified.txt

# Enable verbose debugging
python vf_curve_editor.py my_blob.txt -s 10 -v
```

### Command Line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `blob_source` | Path to blob file, `-` for stdin, or omit for `vf_curve_blob.txt` | `vf_curve_blob.txt` |
| `-s, --shift` | Look-ahead index shift (must be < number of VF entries) | `0` |
| `-f, --foffset` | Additional frequency offset in MHz | `0.0` |
| `-c, --cutoff` | Lock frequencies at or above this voltage (mV) | `None` |
| `-o, --output` | Write result to file instead of stdout | `None` |
| `--validate` | Parse and validate blob without modifying | `False` |
| `-v, --verbose` | Enable debug-level logging | `False` |
| `--version` | Show version information | - |

## Finding Your VF Curve Blob

MSI Afterburner stores VF curve data in configuration files located at:

```
C:\Program Files (x86)\MSI Afterburner\Profiles\VEN_10DE&DEV_XXXX&SUBSYS_XXXXXXXX&REV_XX&BUS_X&DEV_X&FN_X.cfg
```

The filename contains your GPU's hardware IDs:
- `DEV_XXXX` - Device ID (e.g., `1C82` for GTX 1060)
- `SUBSYS_XXXXXXXX` - Subsystem ID
- `REV_XX` - Revision
- `BUS_X`, `DEV_X`, `FN_X` - PCI bus location

To find your specific file:
1. Open MSI Afterburner
2. Make any change to the VF curve (so the file gets written)
3. Navigate to the `Profiles` folder in your MSI Afterburner installation
4. Look for the most recently modified `.cfg` file

## Understanding the Transformations

### Shift Operation

When you apply a shift of `N` steps, the tool:
1. Looks ahead `N` P-states to find the target frequency
2. Sets the new effective frequency to that target + optional offset
3. Calculates the required offset: `new_offset = new_effective_freq - original_freq`

This effectively shifts the entire curve to the right (higher voltages) or left (lower voltages) depending on your shift value.

### Cutoff/Capping

When a cutoff voltage is specified:
1. All entries **below** the cutoff are shifted normally
2. The last shifted entry below the cutoff determines the cap frequency
3. All entries **at or above** the cutoff are locked to this cap frequency

This creates a flat voltage-frequency curve above the cutoff point, useful for:
- Preventing unstable high-voltage operation
- Power limiting
- Temperature control

## Safety Features

The tool includes multiple safety checks:

### Input Validation
- **Voltage**: 400-1250 mV (typical desktop GPU range)
- **Frequency**: 100-3000 MHz (covers current and near-future GPUs)
- **Offset**: -500 to +500 MHz (prevents extreme values)
- Non-finite values (NaN, Inf) are rejected

### Structural Checks
- Hex string format validation
- Proper header length (24 chars)
- Even number of hex characters
- Detection of malformed entries

### Runtime Safeguards
- Shift value must be less than entry count
- Cutoff voltage must be positive
- Preserves original header and trailing padding
- Sentinels remain intact

## Example Workflow

1. **Extract your current curve**:
   ```bash
   # Copy the hex blob from your MSI Afterburner .cfg file to blob.txt
   # Look for a long hex string in the VF curve section
   ```

2. **Validate the blob**:
   ```bash
   python vf_curve_editor.py blob.txt --validate
   ```

3. **Test transformations**:
   ```bash
   # Apply a moderate shift and preview results
   python vf_curve_editor.py blob.txt -s 5 -v
   ```

4. **Apply and save**:
   ```bash
   # Apply shift + offset + cap, save to new file
   python vf_curve_editor.py blob.txt -s 8 -f 10 -c 950 -o modified_blob.txt
   ```

5. **Replace in MSI Afterburner**:
   - Exit MSI Afterburner
   - Back up your original `.cfg` file
   - Replace the hex blob in the `.cfg` file with the modified version
   - Start MSI Afterburner

## Troubleshooting

### "No VF entries found in the blob"
- The blob may be corrupted or from an unsupported GPU generation
- Try extracting the blob again from MSI Afterburner

### "shift must be less than the entry count"
- Your curve has fewer P-states than the requested shift
- Reduce the shift value or use `--validate` to see entry count

### "Blob contains non-hexadecimal characters"
- The input file may contain whitespace, line breaks, or other text
- Ensure you've extracted only the hex string (no spaces, newlines, or labels)

### "Entry X sanity warning"
- The decoded values are outside expected ranges but still valid
- Review the warnings to ensure they match your hardware capabilities

## Technical Notes

- **Endianness**: All floats are little-endian IEEE-754 single-precision
- **Precision**: The tool preserves original float precision throughout transformations
- **Memory Layout**: Original header and padding are preserved exactly
- **Sentinel Handling**: Zero entries are correctly identified as terminators

## Contributing

Feel free to submit issues or pull requests for:
- Support for additional GPU generations
- New transformation algorithms
- Performance improvements
- Additional validation rules

## License

This tool is provided as-is for educational and personal use. Always backup your original configuration files before making changes.

## Version History

- **2.0.0** - Added cutoff/capping functionality, improved validation, RTX 30-series testing
- **1.0.0** - Initial release, GTX 10-series support

## Disclaimer

Overclocking and voltage modification can damage your hardware. Use this tool at your own risk. The author assumes no responsibility for any damage caused by improper use of this software.
