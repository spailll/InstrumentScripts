
"""CLI: python -m usb6001 devices | read | stream | plot"""
from __future__ import annotations
import argparse
import csv
import sys
import time
from pathlib import Path
from collections import deque
from .driver import USB6001Thermocouples, SensorCalibration, CSV_HEADER, available_devices


def make_parser():
    p = argparse.ArgumentParser(description="USB-6001 two-channel AD8495 voltage-to-temperature reader")
    p.add_argument("--device", default="Dev1", help="NI-MAX DAQ name, default Dev1")
    p.add_argument("--channels", nargs=2, type=int, default=[0, 1], metavar=("TC1", "TC2"))
    p.add_argument("--reference-volts", nargs=2, type=float, default=[1.25, 1.25], metavar=("TC1", "TC2"),
                   help="AD8495 REF voltages, default 0 0; use e.g. 1.25 1.25 ONLY if wired that way")
    p.add_argument("--slope", nargs=2, type=float, default=[0.005, 0.005], metavar=("TC1", "TC2"),
                   help="volts per °C, default 0.005 0.005")
    p.add_argument("--offset-c", nargs=2, type=float, default=[0., 0.], metavar=("TC1", "TC2"),
                   help="additional temperature corrections in Celsius")
    p.add_argument("--samples", type=int, default=10, help="voltage readings averaged per channel, default 10")
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser("devices", help="list connected NI DAQ device identifiers")
    sub.add_parser("read", help="single two-channel reading")
    stream = sub.add_parser("stream", help="terminal updates, optional CSV logging")
    plot = sub.add_parser("plot", help="live Matplotlib plot, optional CSV logging")
    for cmd in (stream, plot):
        cmd.add_argument("--interval", type=float, default=1.0, help="seconds between updates")
        cmd.add_argument("--count", type=int, default=0, help="number of updates; 0 = until Ctrl+C")
        cmd.add_argument("--csv", type=Path, help="CSV output file (appended; header added if empty)")
    plot.add_argument("--history", type=int, default=300, help="maximum displayed points")
    return p


def output(m):
    print(f"{m.timestamp_utc} | TC1: {m.tc1_c:8.2f} °C ({m.tc1_f:7.2f} °F) "
          f"[{m.tc1_volts:.5f} V] | TC2: {m.tc2_c:8.2f} °C ({m.tc2_f:7.2f} °F) "
          f"[{m.tc2_volts:.5f} V] | Δ(TC1−TC2): {m.delta_c:+.2f} °C", flush=True)


def main(argv=None):
    args = make_parser().parse_args(argv)
    if args.action == "devices":
        names = available_devices()
        print("\n".join(names) if names else "No NI-DAQmx devices found. Check cable, NI-MAX, and driver installation.")
        return 0 if names else 1
    cal = tuple(SensorCalibration(args.slope[i], args.reference_volts[i], args.offset_c[i]) for i in range(2))
    if args.action in ("stream", "plot") and args.interval <= 0:
        raise ValueError("--interval must be positive")
    if args.action == "plot" and args.history <= 1:
        raise ValueError("--history must be greater than 1")
    daq = USB6001Thermocouples(device=args.device, channels=tuple(args.channels),
                              calibrations=cal, samples_per_read=args.samples)
    if args.action == "read":
        with daq:
            output(daq.read())
        return 0
    writer = None
    handle = None
    try:
        if args.csv:
            args.csv.parent.mkdir(parents=True, exist_ok=True)
            add_header = not args.csv.exists() or args.csv.stat().st_size == 0
            handle = args.csv.open("a", newline="", encoding="utf-8")
            writer = csv.writer(handle)
            if add_header:
                writer.writerow(CSV_HEADER)
                handle.flush()
        if args.action == "plot":
            try:
                import matplotlib.pyplot as plt
            except ImportError as exc:
                raise RuntimeError("Install matplotlib: py -m pip install matplotlib") from exc
            xs, ys1, ys2 = deque(maxlen=args.history), deque(maxlen=args.history), deque(maxlen=args.history)
            fig, ax = plt.subplots()
            l1, = ax.plot([], [], label="TC1 (°C)")
            l2, = ax.plot([], [], label="TC2 (°C)")
            ax.set(xlabel="Elapsed time (s)", ylabel="Temperature (°C)", title="USB-6001 • Thermocouple temperatures")
            ax.grid(True)
            ax.legend()
            plt.show(block=False)
        with daq:
            begin = time.monotonic()
            next_time = begin
            n = 0
            try:
                while not args.count or n < args.count:
                    if args.action == "plot" and not plt.fignum_exists(fig.number):
                        break
                    m = daq.read()
                    output(m)
                    if writer:
                        writer.writerow(m.csv_row())
                        handle.flush()
                    if args.action == "plot":
                        xs.append(time.monotonic() - begin)
                        ys1.append(m.tc1_c)
                        ys2.append(m.tc2_c)
                        l1.set_data(list(xs), list(ys1))
                        l2.set_data(list(xs), list(ys2))
                        ax.relim()
                        ax.autoscale_view()
                        plt.pause(0.01)
                    n += 1
                    next_time += args.interval
                    time.sleep(max(0, next_time - time.monotonic()))
            except KeyboardInterrupt:
                print("\nAcquisition stopped.")
    finally:
        if handle:
            handle.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
