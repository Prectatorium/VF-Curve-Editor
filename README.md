# VF Curve Editor

A Python tool for parsing, editing, and visualizing GPU voltage-frequency (VF) curve blobs (used by MSI Afterburner-style formats).  
Supports CLI, GUI, plotting, and programmatic transformation with configurable curve shaping and offsets.

> Work in progress — expect evolving behavior, missing edge-case hardening, and API tweaks.

## Features

- Parse proprietary VF curve hex blobs into structured data Apply:
  - Step shifting (look-ahead frequency shifting)
  - Flat frequency offset
  - Custom curve shaping (power-based boost curve)
  - Voltage cutoff locking
- Validate blob structure and monotonic voltage ordering
- Serialize modified curves back into original blob format
- CLI output modes:
  - Table view
  - JSON debug export
  - Plot visualization
- GUI editor with live curve preview (Tkinter + Matplotlib)
- Interactive curve comparison plot with hover inspection

## Project Structure

```
cli.py         → Command-line interface
gui.py         → Tkinter GUI editor
model.py       → Core data models & config structures
parser.py      → VF blob parsing & validation
transform.py   → Curve transformation logic
serializer.py  → Rebuild blob from modified entries
plot.py        → Visualization utilities

```

## How It Works (Short Version)

1. **Input blob*- is parsed into VF entries (`voltage`, `frequency`, `offset`)
2. A transformation pipeline is applied:
   - Step shift (index look-ahead)
   - Optional curve boost
   - Flat offset
   - Optional cutoff lock
3. New offsets are computed and clamped to safe ranges
4. Result is serialized back into the original hex blob format

## CLI Usage

### Basic run

```bash
python cli.py vf_curve_blob.txt
````

### Shift curve

```bash
python cli.py blob.txt -s 3
```

### Add frequency offset

```bash
python cli.py blob.txt -f 50
```

### Apply curve shaping

```bash
python cli.py blob.txt --curve-peak 150 --curve-shape 1.5
```

### Output options

```bash
--table        # print debug table
--json         # print debug JSON
--plot         # show curve plot
-o output.txt  # write modified blob
```

### Validation only

```bash
python cli.py blob.txt --validate
```

## GUI Mode

Launch interactive editor:

```bash
python cli.py blob.txt --gui
```

### Controls

- **Shift*- → look-ahead curve shift
- **Peak MHz*- → curve boost amplitude
- **Power*- → curve steepness
- Live preview updates instantly

Click **Commit Changes*- to:

- Save `vf_curve_modified.txt`
- Copy blob to clipboard (if `pyperclip` installed)

## Plot Mode

```bash
python cli.py blob.txt --plot
```

Shows:

- Original VF curve
- Modified curve
- Hover tooltip inspection per point

## Core Concepts

### Shift logic

Each point uses future frequency values:

```py
new_freq[i] = freq[i + shift_steps]
```

### Curve shaping

A normalized voltage curve applies nonlinear boost:

```py
boost = peak_mhz - t^power
```

Where `t` is voltage position between start and end.

### Cutoff mode

Locks frequency after a voltage threshold.

## Constraints

The system enforces:

- Voltage monotonicity
- Frequency bounds (100–3000 MHz)
- Offset bounds (-500 to +500 MHz)
- Safe float validation (no NaN/Inf)
- Blob structural integrity (fixed header + payload)

##  Status

This is still evolving:

- No formal test suite yet
- Parser assumes strict blob format
- GUI is functional but not polished
- Edge cases in malformed blobs may still slip through

## Requirements

- Python 3.10+
- matplotlib
- numpy

Optional:

- pyperclip (clipboard support in GUI)

## Future Ideas

- Preset profiles (OC / undervolt modes)
- Undo/redo stack in GUI
- Real-time GPU telemetry integration
- Safer blob schema validation layer
- Export/import curve presets (JSON)
- Better error diagnostics for corrupted blobs

## Why this exists

Because manually dragging VF curves is pain, and automation should hurt less than GPU instability testing.

## Disclaimer

This tool can affect GPU stability.
If your system starts behaving like a microwave with opinions, that’s on you.
