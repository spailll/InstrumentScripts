
"""Keithley 6485 communication and response-validation diagnostic.

Usage:
    python test_connection.py --port COM4
    python test_connection.py --port COM4 --count 100
    python test_connection.py --port COM4 --measure --samples 10

Default tests do not reset or reconfigure measurement settings.
Measurement acquisition is opt-in with --measure.
"""

from __future__ import annotations

import argparse
import math
import re
import statistics
import sys
import time
from dataclasses import dataclass, field

from keithley6485 import Keithley6485


class DiagnosticFailure(Exception):
    """A communication or validation check failed."""


@dataclass
class Results:
    checks_passed: int = 0
    checks_failed: int = 0
    query_times_ms: list[float] = field(default_factory=list)
    measurements_a: list[float] = field(default_factory=list)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DiagnosticFailure(message)


def validate_idn(response: str) -> None:
    require(
        "KEITHLEY" in response.upper()
        and re.search(
            r"\bMODEL\s*6485\b",
            response,
            re.IGNORECASE
        ) is not None,
        f"Wrong instrument or malformed ID: {response!r}",
    )


def validate_integer(
    response: str,
    expected: int,
    command: str
) -> None:
    require(
        re.fullmatch(r"[+-]?\d+", response.strip()) is not None,
        f"{command} returned non-integer: {response!r}",
    )
    require(
        int(response.strip()) == expected,
        f"{command} returned {response!r}; expected {expected}",
    )


def validate_current(raw: str, amperes: float) -> None:
    first = raw.split(",", 1)[0].strip()

    match = re.fullmatch(
        r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)"
        r"(?:[Ee][+-]?\d+)?)\s*(?:A|ADC)?",
        first,
        flags=re.IGNORECASE,
    )

    require(
        match is not None,
        f"Malformed current response: {raw!r}"
    )

    require(
        math.isfinite(amperes),
        f"Non-finite current: {raw!r}"
    )

    require(
        math.isclose(
            float(match.group(1)),
            amperes,
            rel_tol=1e-12,
            abs_tol=0
        ),
        f"Parsed current disagrees with response: {raw!r}"
    )

    # Reject overflow sentinels and values outside the
    # 6485's approximately 21 mA overrange boundary.
    require(
        abs(amperes) <= 0.021,
        f"Out-of-range / overflow reading: {raw!r}"
    )


def timed_query(
    meter: Keithley6485,
    results: Results,
    command: str
) -> str:
    start = time.perf_counter()
    response = meter.query(command)
    elapsed_ms = (time.perf_counter() - start) * 1000

    results.query_times_ms.append(elapsed_ms)

    require(
        response != "",
        f"Empty response from {command}"
    )

    return response


def perform_check(name, callback, results):
    try:
        detail = callback()

    except Exception as exc:
        results.checks_failed += 1
        print(
            f"[FAIL] {name}: "
            f"{type(exc).__name__}: {exc}",
            flush=True
        )
        raise DiagnosticFailure(
            f"{name} failed"
        ) from exc

    results.checks_passed += 1

    if detail is None:
        print(f"[PASS] {name}", flush=True)
    else:
        print(f"[PASS] {name}: {detail}", flush=True)

    return detail


def run(args):
    result = Results()

    terminators = {
        "lf": "\n",
        "cr": "\r",
        "crlf": "\r\n"
    }

    started = time.perf_counter()

    print(
        f"Keithley 6485 diagnostic | "
        f"{args.port} | {args.baud} baud, 8N1"
    )
    print(
        f"Write terminator: {args.write_term} | "
        f"Read terminator: {args.read_term}"
    )
    print(
        "Close NI MAX / VISA Interactive Control "
        "before testing."
    )
    print("-" * 65)

    try:
        with Keithley6485(
            args.port,
            baud=args.baud,
            timeout_ms=args.timeout,
            parity=args.parity,
            flow_control=args.flow_control,
            write_termination=terminators[args.write_term],
            read_termination=terminators[args.read_term],
        ) as meter:

            print("[PASS] Open VISA serial session")
            result.checks_passed += 1

            # 1. Identify the instrument
            def identity():
                value = timed_query(
                    meter, result, "*IDN?"
                )
                validate_idn(value)
                return value

            idn = perform_check(
                "Identify MODEL 6485",
                identity,
                result
            )

            # 2. Verify operation-complete response
            def opc():
                value = timed_query(
                    meter, result, "*OPC?"
                )
                validate_integer(value, 1, "*OPC?")
                return value

            perform_check(
                "Operation-complete query",
                opc,
                result
            )

            # 3. Internal ROM self-test
            if not args.skip_self_test:

                def rom_self_test():
                    value = timed_query(
                        meter, result, "*TST?"
                    )
                    validate_integer(value, 0, "*TST?")
                    return "ROM checksum OK (0)"

                perform_check(
                    "ROM self-test",
                    rom_self_test,
                    result
                )

            # 4. Check instrument error queue
            # COUN? does not consume queued errors.
            def error_count(label):

                def check():
                    value = timed_query(
                        meter,
                        result,
                        ":SYST:ERR:COUN?"
                    )

                    require(
                        re.fullmatch(
                            r"[+-]?\d+", value
                        ) is not None,
                        f"Malformed error count: {value!r}"
                    )

                    number = int(value)

                    require(
                        number == 0,
                        f"{number} queued error(s). "
                        "Inspect using the CLI error command."
                    )

                    return "0 queued errors"

                perform_check(label, check, result)

            error_count("Error queue (before)")

            # 5. Repeated communication stress test
            print(
                f"\nStress test: {args.count} cycles "
                "of *IDN? + *OPC?"
            )

            for i in range(1, args.count + 1):

                def stress_cycle():
                    response_id = timed_query(
                        meter, result, "*IDN?"
                    )

                    validate_idn(response_id)

                    require(
                        response_id == idn,
                        f"Identity changed: {response_id!r}"
                    )

                    response_opc = timed_query(
                        meter, result, "*OPC?"
                    )

                    validate_integer(
                        response_opc, 1, "*OPC?"
                    )

                perform_check(
                    f"Cycle {i:03d}/{args.count:03d}",
                    stress_cycle,
                    result
                )

                if args.interval and i < args.count:
                    time.sleep(args.interval)

            # 6. Optional actual current measurements
            if args.measure:
                print(
                    f"\nMeasurement validation: "
                    f"{args.samples} readings"
                )

                for i in range(1, args.samples + 1):

                    def measurement():
                        start = time.perf_counter()
                        reading = meter.read_current()

                        elapsed_ms = (
                            time.perf_counter() - start
                        ) * 1000

                        result.query_times_ms.append(
                            elapsed_ms
                        )

                        validate_current(
                            reading.raw,
                            reading.amperes
                        )

                        result.measurements_a.append(
                            reading.amperes
                        )

                        return (
                            f"{reading.amperes:.6e} A "
                            f"({reading.picoamperes:.3f} pA) "
                            f"| {elapsed_ms:.1f} ms "
                            f"| raw={reading.raw!r}"
                        )

                    perform_check(
                        f"Measurement "
                        f"{i:03d}/{args.samples:03d}",
                        measurement,
                        result
                    )

                    if args.interval and i < args.samples:
                        time.sleep(args.interval)

            error_count("Error queue (after)")

    except DiagnosticFailure:
        pass

    except Exception as exc:
        result.checks_failed += 1
        print(
            f"[FAIL] VISA or unexpected exception: "
            f"{type(exc).__name__}: {exc}",
            flush=True
        )

    # Final summary
    elapsed_s = time.perf_counter() - started

    print("\n" + "=" * 65)
    print(
        "RESULT: " +
        ("PASS" if result.checks_failed == 0 else "FAIL")
    )

    print(
        f"Checks passed: {result.checks_passed} | "
        f"failed: {result.checks_failed}"
    )
    print(f"Elapsed: {elapsed_s:.2f} s")

    if result.query_times_ms:
        print(
            "Query latency: "
            f"median "
            f"{statistics.median(result.query_times_ms):.1f} ms"
            f" | max {max(result.query_times_ms):.1f} ms"
            f" | samples {len(result.query_times_ms)}"
        )

    if result.measurements_a:
        values = result.measurements_a

        print(
            f"Current: min {min(values):.6e} A"
            f" | max {max(values):.6e} A"
            f" | mean {statistics.mean(values):.6e} A"
        )

    if result.checks_failed:
        print(
            "A failed query may leave stale response bytes. "
            "Resolve the problem before rerunning."
        )
        return 1

    print(
        "Communication and response-format checks passed."
    )
    print(
        "This does not certify measurement accuracy "
        "or electrical safety."
    )

    return 0


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Keithley 6485 communication "
            "and response-integrity diagnostic"
        )
    )

    parser.add_argument(
        "--port", default="COM4"
    )
    parser.add_argument(
        "--baud", type=int, default=9600
    )
    parser.add_argument(
        "--timeout", type=int, default=10000
    )
    parser.add_argument(
        "--parity",
        choices=["none", "odd", "even"],
        default="none"
    )
    parser.add_argument(
        "--flow-control",
        choices=["none", "rtscts", "xonxoff"],
        default="none"
    )
    parser.add_argument(
        "--write-term",
        choices=["lf", "cr", "crlf"],
        default="lf"
    )
    parser.add_argument(
        "--read-term",
        choices=["lf", "cr", "crlf"],
        default="lf"
    )
    parser.add_argument(
        "--count", type=int, default=25
    )
    parser.add_argument(
        "--interval", type=float, default=0.1
    )
    parser.add_argument(
        "--skip-self-test", action="store_true"
    )
    parser.add_argument(
        "--measure", action="store_true"
    )
    parser.add_argument(
        "--samples", type=int, default=10
    )

    args = parser.parse_args()

    if (
        args.count <= 0
        or args.samples <= 0
        or args.timeout <= 0
        or args.interval < 0
    ):
        parser.error(
            "--count, --samples, and --timeout must "
            "be positive; --interval must be >= 0"
        )

    try:
        return run(args)

    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Test stopped by user.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
