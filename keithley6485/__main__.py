
from __future__ import annotations
import argparse
import csv
from pathlib import Path
import sys
import pyvisa
from .driver import Keithley6485


def main():
    parser = argparse.ArgumentParser(
        description='Keithley 6485 serial control'
    )

    parser.add_argument('--port', default='COM4')
    parser.add_argument('--baud', type=int, default=9600)
    parser.add_argument('--timeout', type=int, default=10000)
    parser.add_argument(
        '--write-term',
        choices=['lf', 'cr', 'crlf'],
        default='lf'
    )
    parser.add_argument(
        '--read-term',
        choices=['lf', 'cr', 'crlf'],
        default='lf'
    )
    parser.add_argument('--backend', default=None)

    sub = parser.add_subparsers(dest='action', required=True)

    sub.add_parser('ports', help='List VISA resources')
    sub.add_parser('id', help='Identify instrument')
    sub.add_parser('read', help='Read current')
    sub.add_parser('error', help='Query error queue')
    sub.add_parser('reset', help='Reset instrument')
    sub.add_parser('clear', help='Clear status')

    command = sub.add_parser('query')
    command.add_argument('scpi')

    command = sub.add_parser('write')
    command.add_argument('scpi')

    cfg = sub.add_parser('configure')
    cfg.add_argument('--range', type=float, dest='range_amperes')
    cfg.add_argument('--nplc', type=float)
    cfg.add_argument('--filter', choices=['on', 'off'])

    stream = sub.add_parser('stream')
    stream.add_argument('--interval', type=float, default=0.5)
    stream.add_argument('--count', type=int)
    stream.add_argument('--csv', type=Path)
    stream.add_argument(
        '--unit',
        choices=['A', 'nA', 'pA'],
        default='pA'
    )

    args = parser.parse_args()

    if args.action == 'ports':
        with (
            pyvisa.ResourceManager(args.backend)
            if args.backend else pyvisa.ResourceManager()
        ) as rm:
            print(
                '\n'.join(rm.list_resources())
                or 'No VISA resources found'
            )
        return 0

    terms = {
        'lf': '\n',
        'cr': '\r',
        'crlf': '\r\n'
    }

    try:
        with Keithley6485(
            args.port,
            baud=args.baud,
            timeout_ms=args.timeout,
            write_termination=terms[args.write_term],
            read_termination=terms[args.read_term],
            backend=args.backend
        ) as meter:

            if args.action == 'id':
                print(meter.identify())

            elif args.action == 'read':
                m = meter.read_current()
                print(
                    f'{m.amperes:.9e} A '
                    f'({m.picoamperes:.3f} pA) '
                    f'raw={m.raw!r}'
                )

            elif args.action == 'error':
                print(meter.error())

            elif args.action == 'reset':
                meter.reset()
                print('Reset command sent')

            elif args.action == 'clear':
                meter.clear_status()
                print('Status cleared')

            elif args.action == 'query':
                print(meter.query(args.scpi))

            elif args.action == 'write':
                meter.write(args.scpi)
                print('Command sent (not instrument acknowledgment)')

            elif args.action == 'configure':
                meter.configure_current(
                    range_amperes=args.range_amperes,
                    nplc=args.nplc,
                    filter_enabled=(
                        None if args.filter is None
                        else args.filter == 'on'
                    )
                )
                print('Configuration commands sent')

            elif args.action == 'stream':
                file = None

                try:
                    if args.csv:
                        args.csv.parent.mkdir(
                            parents=True,
                            exist_ok=True
                        )

                        file = args.csv.open(
                            'w',
                            newline='',
                            encoding='utf-8'
                        )

                        writer = csv.writer(file)
                        writer.writerow([
                            'timestamp_utc',
                            'amperes',
                            'raw'
                        ])

                    for m in meter.stream(
                        interval_s=args.interval,
                        count=args.count
                    ):
                        val = {
                            'A': m.amperes,
                            'nA': m.nanoamperes,
                            'pA': m.picoamperes
                        }[args.unit]

                        print(
                            f'{m.timestamp_utc}  '
                            f'{val:.9g} {args.unit}',
                            flush=True
                        )

                        if file:
                            writer.writerow([
                                m.timestamp_utc,
                                f'{m.amperes:.12g}',
                                m.raw
                            ])
                            file.flush()

                except KeyboardInterrupt:
                    print('\nStopped by user')

                finally:
                    if file:
                        file.close()

    except (
        pyvisa.errors.VisaIOError,
        ValueError,
        RuntimeError
    ) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        print(
            'Check COM port, close NI MAX test panels, '
            'and verify baud/terminators.',
            file=sys.stderr
        )
        return 1

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
