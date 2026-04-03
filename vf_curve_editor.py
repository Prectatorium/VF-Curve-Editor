#!/usr/bin/env python3
"""
VF Curve Editor
===============
Parses, shifts, and optionally caps an MSI Afterburner / NVIDIA VF curve blob.

Blob field semantics (confirmed by hardware testing on RTX 30-series):
  volt   : voltage for this P-state (mV)
  freq   : raw hardware reference frequency (MHz) — never modified by this tool.
  offset : delta added on top of freq at runtime.
             Effective frequency = freq + offset.
             The factory OC on the GAMING X is encoded here.
             Afterburner displays (freq + offset) as the curve position.

Blob layout:
  [HEADER: 24 hex chars / 12 bytes] [N x ENTRY: 24 hex chars / 12 bytes each]
  Each entry is three little-endian IEEE-754 single-precision floats (fff).
  Entries with volt == 0.0 AND freq == 0.0 are treated as sentinels (end of data).

Sanity limits for decoded floats:
  Voltage : 400 - 1250 mV   (typical desktop GPU range)
  Frequency: 100 - 3000 MHz (covers current and near-future GPUs)
  Offset  : -500 - +500 MHz

Usage examples:
  python vf_curve_editor.py                          # use vf_curve_blob.txt in cwd
  python vf_curve_editor.py my_blob.txt -s 10        # shift by 10 steps
  python vf_curve_editor.py my_blob.txt -s 8 -f 15   # shift + 15 MHz extra
  python vf_curve_editor.py my_blob.txt -s 10 -c 900 # cap above 900 mV
  python vf_curve_editor.py my_blob.txt --validate    # check integrity only
  python vf_curve_editor.py - -s 5                   # read blob from stdin
"""

from __future__ import annotations  # allows float | None on Python 3.9

import argparse
import logging
import math
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

# ---------------------------------------------------------------------------
# Format constants
# ---------------------------------------------------------------------------
_FLOAT_STRUCT   = struct.Struct("fff")          # three packed single-precision floats
ENTRY_BYTES     = _FLOAT_STRUCT.size            # 12 bytes per VF entry
ENTRY_HEX_CHARS = ENTRY_BYTES * 2              # 24 hex chars per entry
HEADER_HEX_CHARS = 24                          # 12-byte / 24-hex-char header prefix

# Sanity-check the relationship between constants (catches accidental edits)
assert ENTRY_BYTES == 12,        "ENTRY_BYTES must be 12 (3 x float32)"
assert ENTRY_HEX_CHARS == 24,   "ENTRY_HEX_CHARS must be 24"

# Plausible hardware ranges — entries outside these are flagged as corrupt.
VOLT_MIN_MV,  VOLT_MAX_MV  =  400.0, 1250.0
FREQ_MIN_MHZ, FREQ_MAX_MHZ =  100.0, 3000.0
OFF_MIN_MHZ,  OFF_MAX_MHZ  = -500.0,  500.0

# Default blob file searched when no explicit path is supplied.
DEFAULT_BLOB_FILE = Path("vf_curve_blob.txt")

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class VFEntry:
    """One point on the voltage-frequency curve."""
    index: int
    volt: float          # mV
    freq: float          # MHz (hardware reference; never modified)
    offset: float        # MHz (delta applied at runtime)

    @property
    def effective_freq(self) -> float:
        """Runtime frequency visible to the driver (MHz)."""
        return self.freq + self.offset


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
class BlobError(ValueError):
    """Raised when the blob cannot be parsed or fails a sanity check."""


def _validate_hex_string(blob: str) -> None:
    """
    Raise BlobError if *blob* contains non-hex characters or has an
    impossible length.

    Args:
        blob: Raw hex string (header + entries).

    Raises:
        BlobError: On any structural problem.
    """
    if not blob:
        raise BlobError("Blob is empty.")
    if len(blob) < HEADER_HEX_CHARS:
        raise BlobError(
            f"Blob is too short ({len(blob)} chars); "
            f"minimum is {HEADER_HEX_CHARS} chars for the header alone."
        )
    if len(blob) % 2 != 0:
        raise BlobError(
            f"Blob has an odd number of hex characters ({len(blob)}); "
            "every byte needs two hex digits."
        )
    payload_len = len(blob) - HEADER_HEX_CHARS
    if payload_len % ENTRY_HEX_CHARS != 0:
        log.warning(
            "Payload length (%d chars) is not a multiple of %d; "
            "the blob may be truncated or malformed.",
            payload_len, ENTRY_HEX_CHARS,
        )
    try:
        bytes.fromhex(blob)
    except ValueError as exc:
        raise BlobError(f"Blob contains non-hexadecimal characters: {exc}") from exc


def _check_entry_sanity(entry: VFEntry, *, strict: bool = False) -> list[str]:
    """
    Return a list of human-readable warnings for an entry whose decoded floats
    fall outside the expected hardware range. Returns an empty list if the
    entry looks clean.

    Args:
        entry:  The VFEntry to inspect.
        strict: If True, treat warnings as errors (raises BlobError).
    """
    issues: list[str] = []
    if not (VOLT_MIN_MV <= entry.volt <= VOLT_MAX_MV):
        issues.append(f"voltage {entry.volt:.2f} mV outside [{VOLT_MIN_MV}, {VOLT_MAX_MV}]")
    if not (FREQ_MIN_MHZ <= entry.freq <= FREQ_MAX_MHZ):
        issues.append(f"freq {entry.freq:.2f} MHz outside [{FREQ_MIN_MHZ}, {FREQ_MAX_MHZ}]")
    if not (OFF_MIN_MHZ <= entry.offset <= OFF_MAX_MHZ):
        issues.append(f"offset {entry.offset:.2f} MHz outside [{OFF_MIN_MHZ}, {OFF_MAX_MHZ}]")
    for field_name, value in (("volt", entry.volt), ("freq", entry.freq), ("offset", entry.offset)):
        if math.isnan(value) or math.isinf(value):
            issues.append(f"{field_name} decoded to a non-finite value ({value})")
    if strict and issues:
        raise BlobError(f"Entry {entry.index} failed sanity checks: {'; '.join(issues)}")
    return issues


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def parse_entries(blob: str) -> list[VFEntry]:
    """
    Decode all non-sentinel VF entries from a validated hex blob.

    The function stops at the first entry where both volt and freq are 0.0
    (the sentinel / padding pattern used by Afterburner).

    Args:
        blob: A validated hex string (header already present).

    Returns:
        Ordered list of VFEntry objects.

    Raises:
        BlobError: If a chunk cannot be unpacked.
    """
    entries: list[VFEntry] = []
    pos = HEADER_HEX_CHARS
    index = 0

    while pos + ENTRY_HEX_CHARS <= len(blob):
        chunk = blob[pos : pos + ENTRY_HEX_CHARS]
        try:
            volt, freq, offset = _FLOAT_STRUCT.unpack(bytes.fromhex(chunk))
        except struct.error as exc:
            raise BlobError(
                f"Failed to unpack entry at hex position {pos}: {exc}"
            ) from exc

        if volt == 0.0 and freq == 0.0:
            log.debug("Sentinel found at index %d (hex pos %d); stopping.", index, pos)
            break

        entry = VFEntry(index=index, volt=volt, freq=freq, offset=offset)
        issues = _check_entry_sanity(entry)
        for issue in issues:
            log.warning("Entry %d sanity warning: %s", index, issue)

        entries.append(entry)
        pos += ENTRY_HEX_CHARS
        index += 1

    log.debug("Parsed %d VF entries.", len(entries))
    return entries


# ---------------------------------------------------------------------------
# Transformation
# ---------------------------------------------------------------------------
@dataclass
class ShiftConfig:
    """
    Parameters that control how the VF curve is shifted.

    Attributes:
        shift:         How many P-state steps to look ahead for the target
                       frequency.
        freq_offset:   Extra MHz added on top of the looked-up frequency.
        cutoff_mv:     If set, all entries at or above this voltage are locked
                       to the same effective frequency as the last entry *below*
                       the cutoff (after the shift is applied to that entry).
    """
    shift: int
    freq_offset: float = 0.0
    cutoff_mv: float | None = None


def _validate_shift_config(config: ShiftConfig, entry_count: int) -> None:
    """
    Raise ValueError if the shift configuration is nonsensical given the
    number of available entries.

    Args:
        config:      The shift parameters to validate.
        entry_count: Total number of decoded VF entries.

    Raises:
        ValueError: On any invalid combination.
    """
    if config.shift < 0:
        raise ValueError(f"shift must be ≥ 0, got {config.shift}.")
    if config.shift >= entry_count:
        raise ValueError(
            f"shift ({config.shift}) must be less than the entry count "
            f"({entry_count}); no look-ahead would be possible."
        )
    if config.cutoff_mv is not None and config.cutoff_mv <= 0:
        raise ValueError(f"cutoff_mv must be positive, got {config.cutoff_mv}.")


def compute_shifted_entries(
    entries: list[VFEntry],
    config: ShiftConfig,
) -> list[VFEntry]:
    """
    Return a new list of VFEntry objects with updated offsets according to
    *config*. The volt and freq fields are never modified.

    Shift semantics:
        new_effective_freq[i] = original_effective_freq[i + shift] + freq_offset
        new_offset[i]         = new_effective_freq[i] - freq[i]

    Cutoff semantics:
        Compute the shifted effective frequency for the last entry *below*
        cutoff_mv normally, then lock every entry at or above cutoff_mv to
        that exact frequency.

    Args:
        entries: Parsed, ordered list of VFEntry objects.
        config:  Shift parameters.

    Returns:
        New list of VFEntry objects with updated offsets.
    """
    _validate_shift_config(config, len(entries))

    # Build a fast lookup: index → effective frequency
    eff_freq: dict[int, float] = {e.index: e.effective_freq for e in entries}

    def _target_freq(index: int) -> float:
        lookahead = index + config.shift
        base = eff_freq.get(lookahead, eff_freq[index])   # clamp at the last entry
        return base + config.freq_offset

    shifted: list[VFEntry] = []
    capped_freq: float | None = None  # set once we first cross the cutoff

    for entry in entries:
        at_or_above_cutoff = (
            config.cutoff_mv is not None and entry.volt >= config.cutoff_mv
        )

        if at_or_above_cutoff:
            if capped_freq is None:
                # BUG FIX (vs original): derive cap from the *previous* entry
                # (last below cutoff), already stored in shifted[-1].  This
                # correctly locks everything above to the last-computed
                # shifted value rather than re-applying the shift to the
                # first capped entry.
                capped_freq = shifted[-1].effective_freq if shifted else _target_freq(entry.index)
                log.debug(
                    "Cutoff reached at entry %d (%.2f mV); capping at %.2f MHz.",
                    entry.index, entry.volt, capped_freq,
                )
            new_eff_freq = capped_freq
        else:
            new_eff_freq = _target_freq(entry.index)

        new_offset = new_eff_freq - entry.freq
        shifted.append(
            VFEntry(
                index=entry.index,
                volt=entry.volt,
                freq=entry.freq,
                offset=new_offset,
            )
        )
        log.info(
            "  %7.2f mV  eff=%8.2f MHz  offset=%+.2f MHz%s",
            entry.volt, new_eff_freq, new_offset,
            "  [CAPPED]" if at_or_above_cutoff else "",
        )

    return shifted


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------
def pack_entry(entry: VFEntry) -> str:
    """
    Serialise a single VFEntry back to its 24-character hex representation.

    Args:
        entry: The VFEntry to serialise.

    Returns:
        24-character uppercase hex string (no '0x' prefix).
    """
    return _FLOAT_STRUCT.pack(entry.volt, entry.freq, entry.offset).hex().upper()


def serialise_blob(original_blob: str, shifted_entries: list[VFEntry]) -> str:
    """
    Reconstruct the full blob by replacing the VF payload while keeping the
    original header and any trailing padding unchanged.

    Args:
        original_blob:   The original hex blob string.
        shifted_entries: Transformed entries to embed.

    Returns:
        A new hex blob string of the same total length as the original.
    """
    new_payload = "".join(pack_entry(e) for e in shifted_entries)
    payload_start = HEADER_HEX_CHARS
    payload_end   = payload_start + len(new_payload)

    if payload_end > len(original_blob):
        raise BlobError(
            f"Serialised payload ({len(new_payload)} chars) exceeds "
            f"available space in blob ({len(original_blob) - HEADER_HEX_CHARS} chars)."
        )

    return (
        original_blob[:payload_start]
        + new_payload
        + original_blob[payload_end:]   # preserves sentinel padding exactly
    )


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------
def load_blob(source: str | None) -> str:
    """
    Load and return a hex blob string from one of three sources:
      - None       → read from DEFAULT_BLOB_FILE
      - "-"        → read from stdin
      - <path str> → read from the named file

    Args:
        source: Path string, "-", or None.

    Returns:
        Stripped hex string.

    Raises:
        SystemExit: On any I/O error (user-friendly message).
    """
    if source is None:
        path = DEFAULT_BLOB_FILE
        if not path.exists():
            _die(
                f"No blob argument supplied and default file '{path}' not found.\n"
                "Pass a path to a blob file, or '-' to read from stdin."
            )
        log.info("Loading blob from default file: %s", path)
        return _read_file(path)

    if source == "-":
        log.info("Reading blob from stdin…")
        try:
            return sys.stdin.read().strip()
        except OSError as exc:
            _die(f"Failed to read from stdin: {exc}")

    path = Path(source)
    log.info("Loading blob from file: %s", path)
    return _read_file(path)


def _read_file(path: Path) -> str:
    """Read and strip a file, exiting cleanly on I/O errors."""
    try:
        return path.read_text(encoding="ascii").strip()
    except OSError as exc:
        _die(f"Cannot read '{path}': {exc}")


def write_output(blob: str, destination: str | None) -> None:
    """
    Write *blob* to *destination* (a file path), or print to stdout if
    *destination* is None.

    Args:
        blob:        The final hex blob string.
        destination: File path string, or None for stdout.

    Raises:
        SystemExit: On I/O error.
    """
    if destination is None:
        print(f"\n=== Modified Blob ===\n{blob}")
        return

    path = Path(destination)
    try:
        path.write_text(blob + "\n", encoding="ascii")
        log.info("Result written to: %s", path)
    except OSError as exc:
        _die(f"Cannot write to '{path}': {exc}")


def _die(message: str) -> None:
    """Print an error message and exit with a non-zero status."""
    log.error("%s", message)
    sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Edit an MSI Afterburner VF curve blob.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=(
            "Pass a path to a file containing the hex blob, "
            "'-' to read from stdin, "
            "or omit to load from 'blob.txt' in the current directory."
        ),
    )
    parser.add_argument(
        "blob_source", nargs="?", default=None, metavar="BLOB_FILE",
        help="Path to a file containing the hex blob, or '-' for stdin.",
    )
    parser.add_argument(
        "-s", "--shift", type=int, default=0,
        help="Look-ahead index shift (must be < number of VF entries).",
    )
    parser.add_argument(
        "-f", "--foffset", type=float, default=0.0,
        help="Additional frequency offset (MHz) added on top of the shift.",
    )
    parser.add_argument(
        "-c", "--cutoff", type=float, default=None, metavar="MV",
        help="Lock the frequency for all entries at or above this voltage (mV).",
    )
    parser.add_argument(
        "-o", "--output", default=None, metavar="FILE",
        help="Write the result to FILE instead of stdout.",
    )
    parser.add_argument(
        "--validate", action="store_true",
        help="Parse and validate the blob without modifying it; exit 0 if clean.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug-level logging.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 2.0.0")
    return parser


def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    # --- Load ----------------------------------------------------------------
    raw_blob = load_blob(args.blob_source)

    # --- Validate hex --------------------------------------------------------
    try:
        _validate_hex_string(raw_blob)
    except BlobError as exc:
        _die(str(exc))

    # --- Parse ---------------------------------------------------------------
    try:
        entries = parse_entries(raw_blob)
    except BlobError as exc:
        _die(str(exc))

    if not entries:
        _die("No VF entries found in the blob.")

    log.info("Parsed %d VF entries.", len(entries))

    if args.validate:
        log.info("Validation complete — blob looks clean.")
        return

    # --- Transform -----------------------------------------------------------
    config = ShiftConfig(
        shift=args.shift,
        freq_offset=args.foffset,
        cutoff_mv=args.cutoff,
    )

    print("=== VF Curve Entries ===")
    try:
        shifted_entries = compute_shifted_entries(entries, config)
    except (ValueError, BlobError) as exc:
        _die(str(exc))

    # --- Serialise -----------------------------------------------------------
    try:
        new_blob = serialise_blob(raw_blob, shifted_entries)
    except BlobError as exc:
        _die(str(exc))

    # --- Output --------------------------------------------------------------
    write_output(new_blob, args.output)


if __name__ == "__main__":
    main()
