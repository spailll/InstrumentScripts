
"""Live Keithley 6485 current plotting.

Usage:
    python -m examples.live_plot --port COM4 --prepare-trigger
"""

import argparse
import sys
from collections import deque
from datetime import datetime

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

from keithley6485.arguments import (
    add_connection_arguments,
    open_meter,
)


def main():
    parser = argparse.ArgumentParser(
        description="Keithley 6485 live current plot"
    )

    add_connection_arguments(parser)

    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Requested plot update interval in seconds",
    )

    parser.add_argument(
        "--prepare-trigger",
        action="store_true",
        help="Configure immediate, single-reading trigger",
    )

    parser.add_argument(
        "--read-mode",
        choices=["fresh", "latest"],
        default="fresh",
        help="fresh=READ?, latest=cached last reading",
    )

    args = parser.parse_args()

    if args.interval <= 0:
        parser.error("--interval must be positive")

    times = deque(maxlen=500)
    currents = deque(maxlen=500)

    meter = open_meter(args)

    try:
        meter.connect()

        print(
            "Connected:",
            meter.identify(),
            flush=True
        )

        if args.prepare_trigger:
            meter.prepare_immediate_reading()
            print(
                "Immediate single-reading trigger configured.",
                flush=True
            )

        fig, ax = plt.subplots()

        line, = ax.plot(
            [],
            [],
            marker=".",
            markersize=3
        )

        ax.set_xlabel("Time")
        ax.set_ylabel("Current (pA)")
        ax.set_title("Keithley 6485 — Live Current")

        status = ax.text(
            0.02,
            0.97,
            "Starting...",
            transform=ax.transAxes,
            va="top",
        )

        animation = None
        failures = 0

        def update(_):
            nonlocal failures, animation

            try:
                reading = meter.read_current(
                    mode=args.read_mode
                )

            except Exception as exc:
                failures += 1

                message = (
                    f"Reading failed ({failures}): "
                    f"{type(exc).__name__}: {exc}"
                )

                print(message, file=sys.stderr)
                status.set_text(message[:100])

                # Stop after repeated failures rather than
                # flooding the instrument with commands.
                if failures >= 3:
                    print(
                        "Stopping acquisition after "
                        "3 consecutive failures.",
                        file=sys.stderr
                    )

                    if animation is not None:
                        animation.event_source.stop()

                    status.set_text(
                        "Acquisition stopped: "
                        "3 consecutive failures"
                    )

                return line, status

            failures = 0

            timestamp = datetime.fromisoformat(
                reading.timestamp_utc
            )

            current_pa = reading.picoamperes

            times.append(timestamp)
            currents.append(current_pa)

            line.set_data(
                list(times),
                list(currents)
            )

            ax.relim()
            ax.autoscale_view()
            fig.autofmt_xdate()

            status.set_text(
                f"Current: {current_pa:.3f} pA"
            )

            print(
                f"{reading.timestamp_utc} | "
                f"{reading.amperes:.9e} A | "
                f"{current_pa:.3f} pA",
                flush=True
            )

            return line, status

        animation = FuncAnimation(
            fig,
            update,
            interval=max(
                100,
                int(args.interval * 1000)
            ),
            cache_frame_data=False,
        )

        plt.show()
        return 0

    except Exception as exc:
        print(
            f"Connection/setup error: {exc}",
            file=sys.stderr
        )
        return 1

    finally:
        meter.close()
        print("VISA connection closed.")


if __name__ == "__main__":
    raise SystemExit(main())
