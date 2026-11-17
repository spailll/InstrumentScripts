
"""Shared Keithley 6485 command-line arguments."""

from .driver import Keithley6485

TERMINATORS = {
    "lf": "\n",
    "cr": "\r",
    "crlf": "\r\n",
}


def add_connection_arguments(parser):
    parser.add_argument(
        "--port",
        default="COM4",
        help="Serial port, e.g. COM4"
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=9600
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10000,
        help="VISA timeout in milliseconds"
    )
    parser.add_argument(
        "--write-term",
        choices=TERMINATORS,
        default="lf"
    )
    parser.add_argument(
        "--read-term",
        choices=TERMINATORS,
        default="lf"
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
        "--backend",
        default="@py"
    )


def open_meter(args):
    return Keithley6485(
        args.port,
        baud=args.baud,
        timeout_ms=args.timeout,
        write_termination=TERMINATORS[args.write_term],
        read_termination=TERMINATORS[args.read_term],
        parity=args.parity,
        flow_control=args.flow_control,
        backend=args.backend,
    )
