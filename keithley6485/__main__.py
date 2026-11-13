
"""Keithley 6485 command-line interface."""

import argparse
import csv
import sys
from pathlib import Path

import pyvisa

from .arguments import (
    add_connection_arguments,
    open_meter,
)


def main():
    parser = argparse.ArgumentParser(
        description="Keithley 6485 CLI"
    )

    add_connection_arguments(parser)

    sub = parser.add_subparsers(
        dest="action",
        required=True
    )

    for name in [
        "ports", "id", "error", "reset", "clear"
    ]:
        sub.add_parser(name)

    read = sub.add_parser("read")
    stream = sub.add_parser("stream")

    for command in [read, stream]:
        command.add_argument(
            "--prepare-trigger",
            action="store_true"
        )
        command.add_argument(
            "--read-mode",
            choices=["fresh", "latest"],
            default="fresh"
        )

    stream.add_argument(
        "--interval",
        type=float,
        default=0.5
    )
    stream.add_argument(
        "--count",
        type=int,
        default=None
    )
    stream.add_argument(
        "--csv",
        type=Path
    )
    stream.add_argument(
        "--unit",
        choices=["A", "nA", "pA"],
        default="pA"
    )

    for name in ["query", "write"]:
        command = sub.add_parser(name)
        command.add_argument("scpi")

    cfg = sub.add_parser("configure")
    cfg.add_argument(
        "--range",
        type=float,
        dest="range_amperes"
    )
    cfg.add_argument("--nplc", type=float)
    cfg.add_argument(
        "--filter",
        choices=["on", "off"]
    )

    args = parser.parse_args()

    try:
        if args.action == "ports":
            with pyvisa.ResourceManager(
                args.backend
            ) as rm:
                for resource in rm.list_resources():
                    print(resource)
            return 0

        with open_meter(args) as meter:

            if args.action == "id":
                print(meter.identify())

            elif args.action == "read":
                if args.prepare_trigger:
                    meter.prepare_immediate_reading()

                m = meter.read_current(
                    mode=args.read_mode
                )

                print(
                    f"{m.amperes:.9e} A | "
                    f"{m.picoamperes:.3f} pA"
                )

            elif args.action == "error":
                print(meter.error())

            elif args.action == "reset":
                meter.reset()
                print("Reset command sent")

            elif args.action == "clear":
                meter.clear_status()
                print("Status cleared")

            elif args.action == "query":
                print(meter.query(args.scpi))

            elif args.action == "write":
                meter.write(args.scpi)
                print("Command sent")

            elif args.action == "configure":
                meter.configure_current(
                    range_amperes=args.range_amperes,
                    nplc=args.nplc,
                    filter_enabled=(
                        None
                        if args.filter is None
                        else args.filter == "on"
                    ),
                )
                print("Configuration commands sent")

            elif args.action == "stream":
                if args.interval < 0:
                    parser.error(
                        "--interval must be nonnegative"
                    )

                if args.count is not None and args.count < 1:
                    parser.error(
                        "--count must be positive"
                    )

                if args.prepare_trigger:
                    meter.prepare_immediate_reading()

                csv_file = None

                try:
                    writer = None

                    if args.csv:
                        args.csv.parent.mkdir(
                            parents=True,
                            exist_ok=True
                        )

                        csv_file = args.csv.open(
                            "w",
                            newline="",
                            encoding="utf-8"
                        )

                        writer = csv.writer(csv_file)
                        writer.writerow([
                            "timestamp_utc",
                            "amperes",
                            "raw",
                        ])

                    for m in meter.stream(
                        interval_s=args.interval,
                        count=args.count,
                        mode=args.read_mode,
                    ):
                        value = {
                            "A": m.amperes,
                            "nA": m.nanoamperes,
                            "pA": m.picoamperes,
                        }[args.unit]

                        print(
                            f"{m.timestamp_utc} | "
                            f"{value:.6f} {args.unit}",
                            flush=True
                        )

                        if writer:
                            writer.writerow([
                                m.timestamp_utc,
                                m.amperes,
                                m.raw,
                            ])
                            csv_file.flush()

                except KeyboardInterrupt:
                    print("\nStopped")

                finally:
                    if csv_file:
                        csv_file.close()

        return 0

    except Exception as exc:
        print(
            f"ERROR: {exc}",
            file=sys.stderr
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
