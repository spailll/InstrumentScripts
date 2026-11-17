
"""Two-channel analog-output thermocouple amplifier driver for NI USB-6001.

The DAQ measures VOLTAGE, not a raw thermocouple signal. Default scaling
is for AD8495 with REF tied to GND (V = 0.005 V/°C * T). Verify your
breakout's REF arrangement before trusting temperatures.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import statistics
from typing import Sequence


@dataclass(frozen=True)
class SensorCalibration:
    volts_per_celsius: float = 0.005
    reference_volts: float = 0.0
    temperature_offset_c: float = 0.0

    def __post_init__(self):
        if not math.isfinite(self.volts_per_celsius) or self.volts_per_celsius <= 0:
            raise ValueError("volts_per_celsius must be finite and positive")
        if not math.isfinite(self.reference_volts) or not math.isfinite(self.temperature_offset_c):
            raise ValueError("reference voltage and temperature offset must be finite")

    def to_celsius(self, volts: float) -> float:
        return (volts - self.reference_volts) / self.volts_per_celsius + self.temperature_offset_c


@dataclass(frozen=True)
class TemperatureMeasurement:
    timestamp_utc: str
    tc1_volts: float
    tc2_volts: float
    tc1_c: float
    tc2_c: float

    @property
    def delta_c(self) -> float:
        return self.tc1_c - self.tc2_c

    @property
    def tc1_f(self) -> float:
        return self.tc1_c * 9.0 / 5.0 + 32.0

    @property
    def tc2_f(self) -> float:
        return self.tc2_c * 9.0 / 5.0 + 32.0

    def csv_row(self) -> list[str | float]:
        return [self.timestamp_utc, self.tc1_volts, self.tc2_volts,
                self.tc1_c, self.tc2_c, self.delta_c, self.tc1_f, self.tc2_f]


CSV_HEADER = ["timestamp_utc", "tc1_volts", "tc2_volts", "tc1_c", "tc2_c",
              "delta_c", "tc1_f", "tc2_f"]


def available_devices() -> list[str]:
    """Return NI-DAQmx device names, such as ['Dev1']."""
    try:
        import nidaqmx
    except ImportError as exc:
        raise RuntimeError("Install nidaqmx: py -m pip install nidaqmx") from exc
    return [d.name for d in nidaqmx.system.System.local().devices]


class USB6001Thermocouples:
    """Read two *amplified* thermocouple signals in RSE configuration.

    Usage::
        with USB6001Thermocouples(device='Dev1') as tc:
            print(tc.read())

    Analog inputs are read together in one NI-DAQmx task. `samples_per_read`
    averages consecutive reads to reduce random noise; no promise of
    perfectly simultaneous sampling is made (USB-6001 multiplexes inputs).
    """

    def __init__(self, device: str = "Dev1", channels: tuple[int, int] = (0, 1),
                 calibrations: tuple[SensorCalibration, SensorCalibration] | None = None,
                 samples_per_read: int = 10, voltage_range: tuple[float, float] = (-10.0, 10.0)):
        if len(channels) != 2 or len(set(channels)) != 2 or any(ch not in range(8) for ch in channels):
            raise ValueError("Specify two different USB-6001 analog inputs, 0 through 7")
        if not isinstance(samples_per_read, int) or samples_per_read < 1:
            raise ValueError("samples_per_read must be a positive integer")
        if not (math.isfinite(voltage_range[0]) and math.isfinite(voltage_range[1])
                and voltage_range[0] < voltage_range[1]):
            raise ValueError("Invalid voltage range")
        self.device = device
        self.channels = channels
        self.calibrations = calibrations or (SensorCalibration(), SensorCalibration())
        if len(self.calibrations) != 2:
            raise ValueError("Two calibrations required")
        self.samples_per_read = samples_per_read
        self.voltage_range = voltage_range
        self._task = None

    def connect(self) -> "USB6001Thermocouples":
        if self._task is not None:
            return self
        try:
            import nidaqmx
            from nidaqmx.constants import TerminalConfiguration
        except ImportError as exc:
            raise RuntimeError("Install nidaqmx: py -m pip install nidaqmx") from exc
        task = nidaqmx.Task()
        try:
            for ch in self.channels:
                task.ai_channels.add_ai_voltage_chan(
                    f"{self.device}/ai{ch}", terminal_config=TerminalConfiguration.RSE,
                    min_val=self.voltage_range[0], max_val=self.voltage_range[1])
        except Exception:
            task.close()
            raise
        self._task = task
        return self

    def close(self) -> None:
        if self._task is not None:
            try:
                self._task.close()
            finally:
                self._task = None

    def __enter__(self) -> "USB6001Thermocouples":
        return self.connect()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def read(self) -> TemperatureMeasurement:
        if self._task is None:
            raise RuntimeError("DAQ not connected; use 'with USB6001Thermocouples(...) as daq:'")
        data = self._task.read(number_of_samples_per_channel=self.samples_per_read, timeout=10.0)
        # nidaqmx returns [channel][sample] for multiple channels; each
        # channel is a scalar for one sample and a list for multiple samples.
        if len(data) != 2:
            raise RuntimeError(f"Expected two channels, received {len(data)}")
        volts = [statistics.fmean(d if isinstance(d, (list, tuple)) else [d]) for d in data]
        return TemperatureMeasurement(
            timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            tc1_volts=volts[0], tc2_volts=volts[1],
            tc1_c=self.calibrations[0].to_celsius(volts[0]),
            tc2_c=self.calibrations[1].to_celsius(volts[1]),
        )
