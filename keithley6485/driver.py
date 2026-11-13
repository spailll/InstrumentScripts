
"""Minimal SCPI driver for the Keithley 6485 picoammeter via PyVISA."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import re
import time
import pyvisa
from pyvisa import constants

_NUM = re.compile(r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?')


@dataclass(frozen=True)
class Measurement:
    timestamp_utc: str
    amperes: float
    raw: str

    @property
    def picoamperes(self) -> float:
        return self.amperes * 1e12

    @property
    def nanoamperes(self) -> float:
        return self.amperes * 1e9


class Keithley6485:
    def __init__(
        self,
        port: str,
        *,
        baud: int = 9600,
        timeout_ms: int = 10000,
        write_termination: str = '\n',
        read_termination: str = '\n',
        parity: str = 'none',
        stop_bits: int = 1,
        flow_control: str = 'none',
        backend: str | None = None
    ):
        self.port = port
        self.baud = baud
        self.timeout_ms = timeout_ms
        self.write_termination = write_termination
        self.read_termination = read_termination
        self.parity = parity.lower()
        self.stop_bits = stop_bits
        self.flow_control = flow_control.lower()
        self.backend = backend
        self._rm = None
        self._inst = None

    @staticmethod
    def resource_name(port: str) -> str:
        p = port.strip()

        if p.upper().startswith('ASRL') and p.upper().endswith('::INSTR'):
            return p

        if p.upper().startswith('COM') and p[3:].isdigit():
            return f'ASRL{int(p[3:])}::INSTR'

        raise ValueError('Port must be COM4 or ASRL4::INSTR (for example)')

    def connect(self):
        if self._inst is not None:
            return self

        rm = (
            pyvisa.ResourceManager(self.backend)
            if self.backend else pyvisa.ResourceManager()
        )

        try:
            inst = rm.open_resource(self.resource_name(self.port))
            inst.baud_rate = self.baud
            inst.data_bits = 8

            inst.parity = {
                'none': constants.Parity.none,
                'odd': constants.Parity.odd,
                'even': constants.Parity.even
            }[self.parity]

            inst.stop_bits = {
                1: constants.StopBits.one,
                2: constants.StopBits.two
            }[self.stop_bits]

            inst.flow_control = {
                'none': constants.VI_ASRL_FLOW_NONE,
                'rtscts': constants.VI_ASRL_FLOW_RTS_CTS,
                'xonxoff': constants.VI_ASRL_FLOW_XON_XOFF
            }[self.flow_control]

            inst.timeout = self.timeout_ms
            inst.write_termination = self.write_termination
            inst.read_termination = self.read_termination

        except Exception:
            try:
                inst.close()
            except Exception:
                pass
            rm.close()
            raise

        self._rm, self._inst = rm, inst
        return self

    def close(self):
        try:
            if self._inst is not None:
                self._inst.close()
        finally:
            self._inst = None

            if self._rm is not None:
                self._rm.close()
                self._rm = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc, tb):
        self.close()

    @property
    def instrument(self):
        if self._inst is None:
            raise RuntimeError(
                'Instrument is not connected; '
                'use with Keithley6485(...) as meter:'
            )
        return self._inst

    def write(self, command: str) -> None:
        # PyVISA appends the configured write terminator.
        self.instrument.write(command.rstrip('\r\n'))

    def query(self, command: str) -> str:
        return self.instrument.query(command.rstrip('\r\n')).strip()

    def identify(self) -> str:
        return self.query('*IDN?')

    def reset(self) -> None:
        self.write('*RST')

    def clear_status(self) -> None:
        self.write('*CLS')

    def error(self) -> str:
        return self.query(':SYST:ERR?')

    def configure_current(
        self,
        *,
        autorange: bool = True,
        range_amperes: float | None = None,
        nplc: float | None = None,
        filter_enabled: bool | None = None
    ) -> None:
        self.write(':SENS:FUNC "CURR"')

        if range_amperes is not None:
            if range_amperes <= 0:
                raise ValueError('range_amperes must be positive')

            self.write(':SENS:CURR:RANG:AUTO OFF')
            self.write(f':SENS:CURR:RANG {range_amperes:.12g}')
        else:
            self.write(
                f':SENS:CURR:RANG:AUTO {"ON" if autorange else "OFF"}'
            )

        if nplc is not None:
            if nplc <= 0:
                raise ValueError('nplc must be positive')

            self.write(f':SENS:CURR:NPLC {nplc:.12g}')

        if filter_enabled is not None:
            self.write(
                f':SENS:AVER:STAT {"ON" if filter_enabled else "OFF"}'
            )

    @staticmethod
    def parse_amperes(response: str) -> float:
        first_field = response.split(',')[0].strip()
        match = _NUM.search(first_field)

        if not match:
            raise ValueError(
                f'Cannot parse current from instrument response: {response!r}'
            )

        return float(match.group())
    
    def read_current(self, mode: str = "fresh") -> Measurement:
        """Read current in amperes.

        fresh: READ? triggers a new measurement.
        latest: SENS:DATA? returns the last available reading.
                It may be stale.
        """
        commands = {
            "fresh": ":READ?",
            "latest": ":SENS:DATA?",
        }

        if mode not in commands:
            raise ValueError(
                "mode must be 'fresh' or 'latest'"
            )

        raw = self.query(commands[mode])
        amps = self.parse_amperes(raw)

        if not math.isfinite(amps) or abs(amps) > 0.021:
            raise ValueError(
                f"Invalid/overflow current reading: {raw!r}"
            )

        return Measurement(
            datetime.now(timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            amps,
            raw,
        )



    def stream(
        self,
        *,
        interval_s: float = 0.5,
        count: int | None = None,
        mode: str = "fresh",
    ):
        if interval_s < 0:
            raise ValueError("interval_s must be >= 0")

        if count is not None and count < 1:
            raise ValueError("count must be >= 1")

        i = 0

        while count is None or i < count:
            start = time.monotonic()

            yield self.read_current(mode=mode)

            i += 1
            elapsed = time.monotonic() - start
            time.sleep(max(0, interval_s - elapsed))


    def prepare_immediate_reading(self) -> None:
        """Configure one immediate trigger per READ? command.

        Changes trigger settings but does not reset measurement ranges.
        """
        self.write(":ABOR")
        self.write(":ARM:SOUR IMM")
        self.write(":ARM:COUN 1")
        self.write(":TRIG:SOUR IMM")
        self.write(":TRIG:COUN 1")
        self.write(":TRIG:DEL:AUTO OFF")
        self.write(":TRIG:DEL 0")