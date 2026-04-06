from __future__ import annotations

import struct
from typing import Sequence

from .model import VFEntry, BlobError

# ---------------------------------------------------------------------------
# Format constants (must match parser)
# ---------------------------------------------------------------------------

_FLOAT_STRUCT    = struct.Struct("fff")
ENTRY_BYTES      = _FLOAT_STRUCT.size          # 12 bytes
ENTRY_HEX_CHARS  = ENTRY_BYTES * 2             # 24 hex chars
HEADER_HEX_CHARS = 24                          # 12 bytes


# ---------------------------------------------------------------------------
# Packing
# ---------------------------------------------------------------------------

def pack_entry(entry: VFEntry) -> str:
    """
    Serialize a single VFEntry into hex (uppercase).
    """
    return _FLOAT_STRUCT.pack(
        entry.volt,
        entry.freq,
        entry.offset,
    ).hex().upper()


def build_payload(entries: Sequence[VFEntry]) -> str:
    """
    Build hex payload (without header) from entries.
    """
    return "".join(pack_entry(e) for e in entries)


# ---------------------------------------------------------------------------
# Blob reconstruction
# ---------------------------------------------------------------------------

def serialize_blob(
    original_blob_hex: str,
    entries: Sequence[VFEntry],
) -> str:
    """
    Replace payload section of blob with new entries.

    Keeps:
        - original header
        - any trailing unused space (after payload)

    Fails if:
        - new payload does not fit into original blob
    """

    if len(original_blob_hex) < HEADER_HEX_CHARS:
        raise BlobError("Original blob too short to contain header.")

    new_payload = build_payload(entries)

    payload_start = HEADER_HEX_CHARS
    payload_end   = payload_start + len(new_payload)

    available_payload_size = len(original_blob_hex) - HEADER_HEX_CHARS

    if len(new_payload) > available_payload_size:
        raise BlobError(
            f"New payload ({len(new_payload)} chars) exceeds available space "
            f"({available_payload_size} chars)."
        )

    return (
        original_blob_hex[:payload_start]
        + new_payload
        + original_blob_hex[payload_end:]
    )


# ---------------------------------------------------------------------------
# Integrity helpers (optional but useful)
# ---------------------------------------------------------------------------

def assert_roundtrip_safe(
    original_blob_hex: str,
    entries: Sequence[VFEntry],
) -> None:
    """
    Debug helper:
    Ensures that serializing parsed entries does not overflow
    and preserves structure constraints.
    """
    new_blob = serialize_blob(original_blob_hex, entries)

    if len(new_blob) != len(original_blob_hex):
        raise BlobError(
            "Roundtrip changed blob length — this should never happen."
        )
