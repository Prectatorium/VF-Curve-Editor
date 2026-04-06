from __future__ import annotations

from typing import List, Sequence, Tuple, Optional

from .model import (
    VFEntry,
    ShiftConfig,
    CurveConfig,
    EntryComputation,
    OFF_MIN_MHZ,
    OFF_MAX_MHZ,
    FLOAT_EPSILON,
)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_shift_config(config: ShiftConfig, entry_count: int) -> None:
    if config.shift_steps < 0:
        raise ValueError(f"shift_steps must be >= 0, got {config.shift_steps}")

    if config.shift_steps >= entry_count:
        raise ValueError(
            f"shift_steps ({config.shift_steps}) must be < number of entries ({entry_count})"
        )

    if config.cutoff_voltage_mv is not None and config.cutoff_voltage_mv <= 0:
        raise ValueError(
            f"cutoff_voltage_mv must be positive, got {config.cutoff_voltage_mv}"
        )


def _resolve_curve_bounds(
    curve: CurveConfig,
    entries: Sequence[VFEntry],
) -> Tuple[float, float]:
    start = curve.start_mv if curve.start_mv is not None else entries[0].volt
    end   = curve.end_mv   if curve.end_mv   is not None else entries[-1].volt

    if end <= start:
        raise ValueError(
            f"Curve end voltage ({end:.2f}) must be > start voltage ({start:.2f})"
        )

    return start, end


def _compute_curve_boost(
    curve: CurveConfig,
    voltage_mv: float,
    start_mv: float,
    end_mv: float,
) -> float:
    if not curve.is_enabled or curve.peak_mhz is None:
        return 0.0

    voltage_range = end_mv - start_mv

    if abs(voltage_range) < FLOAT_EPSILON:
        return 0.0

    t = (voltage_mv - start_mv) / voltage_range
    t = max(0.0, min(1.0, t))

    return curve.peak_mhz * (t ** curve.power)


# ---------------------------------------------------------------------------
# Core transformation
# ---------------------------------------------------------------------------

def apply_shift_to_entries(
    entries: Sequence[VFEntry],
    config: ShiftConfig,
) -> Tuple[List[VFEntry], List[EntryComputation]]:
    """
    Apply shift + flat offset + curve shaping + cutoff.

    Returns:
        (new_entries, debug_info)
    """

    if not entries:
        raise ValueError("entries must not be empty")

    _validate_shift_config(config, len(entries))

    # Precompute effective frequencies
    effective_freqs = [e.effective_freq for e in entries]
    last_index = len(entries) - 1

    # Curve setup
    curve = config.curve_config
    start_mv: float = 0.0
    end_mv: float = 0.0

    if curve.is_enabled:
        if curve.power <= 0.0:
            raise ValueError(f"curve power must be > 0, got {curve.power}")

        start_mv, end_mv = _resolve_curve_bounds(curve, entries)

    results: List[VFEntry] = []
    debug: List[EntryComputation] = []

    capped_value: Optional[float] = None

    for i, entry in enumerate(entries):
        # --- Step 1: look-ahead shift
        lookahead_index = min(i + config.shift_steps, last_index)
        base_freq = effective_freqs[lookahead_index]

        # --- Step 2: curve boost
        boost = _compute_curve_boost(curve, entry.volt, start_mv, end_mv)

        # --- Step 3: flat offset
        target_freq = base_freq + config.flat_offset_mhz + boost

        # --- Step 4: cutoff handling
        capped = False
        if config.cutoff_voltage_mv is not None and entry.volt >= config.cutoff_voltage_mv:
            if capped_value is None:
                capped_value = results[-1].effective_freq if results else target_freq
            target_freq = capped_value
            capped = True

        # --- Step 5: compute + clamp offset
        new_offset = target_freq - entry.freq
        new_offset = max(OFF_MIN_MHZ, min(OFF_MAX_MHZ, new_offset))

        new_entry = VFEntry(
            index=entry.index,
            volt=entry.volt,
            freq=entry.freq,
            offset=new_offset,
        )

        results.append(new_entry)

        debug.append(EntryComputation(
            index=entry.index,
            voltage=entry.volt,
            base_freq=base_freq,
            new_freq=target_freq,
            offset=new_offset,
            boost=boost,
            capped=capped,
        ))

    return results, debug
