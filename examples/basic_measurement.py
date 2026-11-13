
"""Basic Keithley 6485 measurement script."""

import argparse
import sys

from keithley6485.arguments import (
    add_connection_arguments,
    open_meter,
)


def main():
    parser = argparse.ArgumentParser(
        description="Keithley 6485 basic measurements"
    )

    add_connection_arguments(parser)

    parser.add_argument(
        "--count",
        type=int,
        default=10
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=1.0
    )

    parser.add_argument(
        "--prepare-trigger",
        action="store_true"
    )

    parser.add_argument(
        "--read-mode",
        choices=["fresh", "latest"],
        default="fresh"
    )

    args = parser.parse_args()

    if args.count < 1 or args.interval < 0:
        parser.error("Invalid count or interval")

    try:
        with open_meter(args) as meter:

            print("Connected:", meter.identify())

            if args.prepare_trigger:
                meter.prepare_immediate_reading()

            for reading in meter.stream(
                interval_s=args.interval,
                count=args.count,
                mode=args.read_mode,
            ):
                print(
                    f"{reading.timestamp_utc} | "
                    f"{reading.amperes:.9e} A | "
                    f"{reading.picoamperes:.3f} pA"
                )

        return 0

    except Exception as exc:
        print(
            f"Measurement error: {exc}",
            file=sys.stderr
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
