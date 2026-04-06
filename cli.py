from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .model import ShiftConfig, CurveConfig, BlobError
from .parser import parse_entries
from .transform import apply_shift_to_entries
from .serializer import serialize_blob


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def load_blob(source: str | None) -> str:
    if source is None:
        path = Path("vf_curve_blob.txt")
        if not path.exists():
            _exit(f"Default file '{path}' not found.")
        return path.read_text(encoding="ascii").strip()

    if source == "-":
        return sys.stdin.read().strip()

    path = Path(source)
    if not path.exists():
        _exit(f"File not found: {path}")

    return path.read_text(encoding="ascii").strip()


def write_output(blob: str, output: str | None) -> None:
    if output is None:
        print("\n=== Modified Blob ===\n")
        print(blob)
        return

    Path(output).write_text(blob + "\n", encoding="ascii")
    log.info("Written to %s", output)


def _exit(msg: str) -> None:
    log.error(msg)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def print_table(debug):
    print("\nIdx | Volt | Base | New  | Offset | Boost | Flags")
    print("-" * 60)

    for d in debug:
        flags = "CAPPED" if d.capped else ""
        print(
            f"{d.index:3d} | "
            f"{d.voltage:6.1f} | "
            f"{d.base_freq:6.1f} | "
            f"{d.new_freq:6.1f} | "
            f"{d.offset:7.1f} | "
            f"{d.boost:6.1f} | "
            f"{flags}"
        )


def print_json(debug):
    print(json.dumps([d.__dict__ for d in debug], indent=2))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Edit an MSI Afterburner VF curve blob.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    p.add_argument("blob_source", nargs="?", default=None)

    # shift
    p.add_argument("-s", "--shift", type=int, default=0)
    p.add_argument("-f", "--foffset", type=float, default=0.0)
    p.add_argument("-c", "--cutoff", type=float)

    # curve
    p.add_argument("--curve-peak", type=float)
    p.add_argument("--curve-shape", type=float, default=1.0)
    p.add_argument("--curve-start-mv", type=float)
    p.add_argument("--curve-end-mv", type=float)

    # output
    p.add_argument("-o", "--output")
    p.add_argument("--table", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--validate", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    try:
        blob = load_blob(args.blob_source)

        entries = parse_entries(blob)

        log.info("Parsed %d entries", len(entries))

        if args.validate:
            log.info("Validation successful")
            return

        config = ShiftConfig(
            shift_steps=args.shift,
            flat_offset_mhz=args.foffset,
            cutoff_voltage_mv=args.cutoff,
            curve_config=CurveConfig(
                peak_mhz=args.curve_peak,
                power=args.curve_shape,
                start_mv=args.curve_start_mv,
                end_mv=args.curve_end_mv,
            ),
        )

        new_entries, debug = apply_shift_to_entries(entries, config)

        new_blob = serialize_blob(blob, new_entries)

        if args.table:
            print_table(debug)

        if args.json:
            print_json(debug)

        write_output(new_blob, args.output)

    except (ValueError, BlobError) as e:
        _exit(str(e))
    except KeyboardInterrupt:
        _exit("Interrupted")


if __name__ == "__main__":
    main()
