# VF Curve Editor

A tool for parsing, modifying, and rebuilding NVIDIA / MSI Afterburner VF curve blobs.

Supports deterministic curve shifting, parametric shaping, and serialization back into the original binary format.

---

## Features

- **Robust parsing**

  - Validates hex blobs and detects malformed entries
  - Handles sentinel termination safely

- **Deterministic transformations**

  - Look-ahead shift (P-state remapping)
  - Flat frequency offsets
  - Parametric curve shaping (power curve)
  - Voltage cutoff capping

- **Advanced curve control**

  - Linear / convex / concave shaping
  - Composable with shift + offset

- **Safety-first design**

  - Output clamping (prevents invalid offsets)
  - Voltage order validation
  - Strict serialization bounds

- **Debug-friendly output**

  - Table view (`--table`)
  - JSON export (`--json`)

---

## Installation

### Option 1 — Run directly

```bash
python -m vfcurve.cli vf_curve_blob.txt --table
```

---

### Option 2 — Build executable

Using PyInstaller:

```bash
pip install pyinstaller
pyinstaller --onefile -n vfcurve -m vfcurve.cli
```

Run:

```bash
./dist/vfcurve vf_curve_blob.txt --table
```

---

## Usage

### Basic

```bash
vfcurve my_blob.txt
```

---

### Shift curve

```bash
vfcurve my_blob.txt -s 10
```

---

### Shift + flat offset

```bash
vfcurve my_blob.txt -s 8 -f 15
```

---

### Voltage cutoff

```bash
vfcurve my_blob.txt -s 10 -c 900
```

---

### Curve shaping

```bash
vfcurve my_blob.txt \
  --curve-peak 100 \
  --curve-shape 2.0 \
  --curve-start-mv 700 \
  --curve-end-mv 1000
```

---

### Combined

```bash
vfcurve my_blob.txt \
  -s 5 \
  --curve-peak 50 \
  --curve-shape 0.5
```

---

### Debug output

#### Table view

```bash
vfcurve my_blob.txt --table
```

#### JSON output

```bash
vfcurve my_blob.txt --json
```

---

## How it works

Each VF entry consists of:

- `volt` (mV)
- `freq` (base MHz)
- `offset` (runtime delta)

Effective frequency:

```py
effective = freq + offset
```

---

### Transformation pipeline

For each entry:

1. **Look-ahead shift**
2. **Flat offset**
3. **Curve boost**
4. **Cutoff cap**
5. **Offset clamp**

---

### Curve shaping formula

```py
t     = clamp((volt - start_mv) / (end_mv - start_mv), 0, 1)
boost = peak_mhz - t^power
```

- `power = 1.0` → linear
- `< 1.0` → convex (front-loaded)
- `> 1.0` → concave (back-loaded)

---

## Safety notes

- Output offsets are clamped to safe hardware limits
- Blob size is never changed
- Invalid blobs will fail fast (no silent corruption)

---

## Development

Project structure:

```bash
vfcurve/
  model.py
  parser.py
  transform.py
  serializer.py
  cli.py
```

---

## Future ideas

- Curve visualization (matplotlib)
- CSV import/export
- GUI frontend
