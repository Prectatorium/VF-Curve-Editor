from __future__ import annotations

import logging
import struct
import math
from typing import List

from .model import (
    VFEntry,
    BlobError,
    FLOAT_EPSILON,
    VOLT_MIN_MV, VOLT_MAX_MV,
    FREQ_MIN_MHZ, FREQ_MAX_MHZ,
    OFF_MIN_MHZ, OFF_MAX_MHZ,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Format constants
# ---------------------------------------------------------------------------

_FLOAT_STRUCT    = struct.Struct("fff")
ENTRY_BYTES      = _FLOAT_STRUCT.size          # 12 bytes
ENTRY_HEX_CHARS  = ENTRY_BYTES * 2             # 24 hex chars
HEADER_HEX_CHARS = 24                          # fixed header size


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_hex_string(blob_hex: str) -> None:
    if not blob_hex:
        raise BlobError("Blob is empty.")

    if len(blob_hex) < HEADER_HEX_CHARS:
        raise BlobError(
            f"Blob too short ({len(blob_hex)} chars); "
            f"needs at least {HEADER_HEX_CHARS}."
        )

    if len(blob_hex) % 2 != 0:
        raise BlobError(
            f"Blob has odd length ({len(blob_hex)}); must be even."
        )

    payload_len = len(blob_hex) - HEADER_HEX_CHARS
    if payload_len % ENTRY_HEX_CHARS != 0:
        log.warning(
            "Payload length (%d) is not multiple of entry size (%d).",
            payload_len, ENTRY_HEX_CHARS
        )

    try:
        bytes.fromhex(blob_hex)
    except ValueError as exc:
        raise BlobError(f"Non-hex characters in blob: {exc}") from exc


def is_sentinel(voltage: float, frequency: float) -> bool:
    return abs(voltage) < FLOAT_EPSILON and abs(frequency) < FLOAT_EPSILON


def get_entry_issues(entry: VFEntry) -> List[str]:
    issues: List[str] = []

    if not (VOLT_MIN_MV <= entry.volt <= VOLT_MAX_MV):
        issues.append(f"voltage {entry.volt:.2f} mV out of range")

    if not (FREQ_MIN_MHZ <= entry.freq <= FREQ_MAX_MHZ):
        issues.append(f"freq {entry.freq:.2f} MHz out of range")

    if not (OFF_MIN_MHZ <= entry.offset <= OFF_MAX_MHZ):
        issues.append(f"offset {entry.offset:.2f} MHz out of range")

    for name, value in (
        ("volt", entry.volt),
        ("freq", entry.freq),
        ("offset", entry.offset),
    ):
        if math.isnan(value) or math.isinf(value):
            issues.append(f"{name} is non-finite ({value})")

    return issues


def validate_voltage_order(entries: List[VFEntry]) -> None:
    for i in range(len(entries) - 1):
        if entries[i].volt > entries[i + 1].volt:
            raise BlobError(
                f"Voltage not monotonic at index {i}: "
                f"{entries[i].volt} > {entries[i+1].volt}"
            )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_entries(blob_hex: str) -> List[VFEntry]:
    validate_hex_string(blob_hex)

    entries: List[VFEntry] = []

    pos = HEADER_HEX_CHARS
    index = 0

    while pos + ENTRY_HEX_CHARS <= len(blob_hex):
        chunk = blob_hex[pos:pos + ENTRY_HEX_CHARS]

        try:
            voltage, frequency, offset = _FLOAT_STRUCT.unpack(
                bytes.fromhex(chunk)
            )
        except struct.error as exc:
            raise BlobError(
                f"Failed to unpack entry at position {pos}: {exc}"
            ) from exc

        if is_sentinel(voltage, frequency):
            log.debug("Sentinel at index %d (pos %d)", index, pos)
            break

        entry = VFEntry(
            index=index,
            volt=voltage,
            freq=frequency,
            offset=offset,
        )

        issues = get_entry_issues(entry)
        for issue in issues:
            log.warning("Entry %d: %s", index, issue)

        entries.append(entry)

        pos += ENTRY_HEX_CHARS
        index += 1

    if not entries:
        raise BlobError("No VF entries found in blob.")

    validate_voltage_order(entries)

    log.debug("Parsed %d entries.", len(entries))
    return entries
