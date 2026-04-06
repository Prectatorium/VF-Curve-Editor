from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FLOAT_EPSILON = 1e-6

VOLT_MIN_MV,  VOLT_MAX_MV  = 400.0, 1250.0
FREQ_MIN_MHZ, FREQ_MAX_MHZ = 100.0, 3000.0
OFF_MIN_MHZ,  OFF_MAX_MHZ  = -500.0, 500.0


# ---------------------------------------------------------------------------
# Core data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VFEntry:
    """One point on the voltage-frequency curve."""
    index: int
    volt: float
    freq: float
    offset: float

    @property
    def effective_freq(self) -> float:
        return self.freq + self.offset


# ---------------------------------------------------------------------------
# Curve configuration
# ---------------------------------------------------------------------------

@dataclass
class CurveConfig:
    peak_mhz: Optional[float] = None
    power: float = 1.0
    start_mv: Optional[float] = None
    end_mv: Optional[float] = None

    @property
    def is_enabled(self) -> bool:
        return self.peak_mhz is not None


# ---------------------------------------------------------------------------
# Shift configuration
# ---------------------------------------------------------------------------

@dataclass
class ShiftConfig:
    shift_steps: int
    flat_offset_mhz: float = 0.0
    cutoff_voltage_mv: Optional[float] = None
    curve_config: CurveConfig = field(default_factory=CurveConfig)


# ---------------------------------------------------------------------------
# Debug / analysis model
# ---------------------------------------------------------------------------

@dataclass
class EntryComputation:
    index: int
    voltage: float
    base_freq: float
    new_freq: float
    offset: float
    boost: float
    capped: bool


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class BlobError(ValueError):
    """Raised when blob parsing or validation fails."""
