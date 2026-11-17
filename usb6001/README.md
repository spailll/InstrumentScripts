
# NI USB-6001 + two amplified thermocouples

This module reads the **analog voltage outputs** from two AD8495-based
thermocouple amplifiers, connected to AI0 and AI1 in referenced single-ended
(RSE) mode. It does **not** read a thermocouple directly or control an AO pin.

## Wiring

- Amplifier 1 OUT -> AI0; amplifier 2 OUT -> AI1
- Each amplifier analog ground -> USB-6001 AI GND
- Amplifier VCC -> 5 V (only if the actual board supports 5 V and total current is within the USB-6001 150 mA supply limit)
- Amplifier supply ground -> USB-6001 D GND (shared ground as required by amplifier board)
- Verify any REF / offset circuitry on your actual amplifier board before using the formula.
- **Do not use this nonisolated DAQ + amplifier on an energized plate or grounded thermocouple attached to an energized surface.** Use an appropriate rated isolated measurement system.

## Install (Windows)

Install NI-DAQmx from NI first; check that the USB-6001 appears in NI MAX.
Then from the `instrumentScripts` folder:

```powershell
py -m pip install -r requirements.txt
py -m usb6001 devices
py -m usb6001 read
py -m usb6001 stream --interval 1 --csv logs/plate_test.csv
py -m usb6001 plot --interval 0.5 --csv logs/plate_test.csv
```

The NI device name might not be `Dev1`. Use `--device Dev2` (before the subcommand)
if NI MAX reports a different name, e.g. `py -m usb6001 --device Dev2 read`.
Press Ctrl+C to end a stream; close the window to end a plot.

Optional flags (place **before** `read`/`stream`/`plot`):

```powershell
# Amplifier board has REF deliberately wired to +1.25 V:
py -m usb6001 --reference-volts 1.25 1.25 read
# Correct two calibrated temperature offsets in Celsius:
py -m usb6001 --offset-c -0.5 0.8 stream --interval 2
# Swap or change the physical analog channels:
py -m usb6001 --channels 1 0 read
# Average 50 voltage samples per channel on each update:
py -m usb6001 --samples 50 read
# Stop automatically after 120 records:
py -m usb6001 stream --interval 1 --count 120 --csv logs/run.csv
```

## Scaling — verify before measurement

**Bare AD8495**: `Vout ≈ VREF + (0.005 V/°C) × Thot`; therefore
`Thot ≈ (Vout − VREF) / 0.005`. With REF tied to ground, nominal `VREF=0`.
**1.25 V is not an automatic AD8495 offset**; a breakout may implement
its own reference network. Verify with a DMM and a reference temperature.
The linear model is approximate; ADI documents thermocouple nonlinearity and
calibration effects. `--offset-c` corrects a constant calibration bias;
`--slope` adjusts gain per channel. Hardware cold-junction compensation is
performed by the amplifier (subject to its mounting and thermal conditions).

`--samples` averages multiple voltage measurements from each channel; it
is not a calibrated thermocouple accuracy guarantee. The two channels are
multiplexed, not simultaneous. Logging timestamps refer to the read operation.

## CLI

- `devices`: list DAQmx devices
- `read`: one sample batch, both thermocouples
- `stream`: terminal output and optional CSV
- `plot`: live matplotlib plot plus optional CSV

CSV columns: timestamp_utc, tc1_volts, tc2_volts, tc1_c, tc2_c,
delta_c, tc1_f, tc2_f.

## Programmatic use

```python
from usb6001 import USB6001Thermocouples, SensorCalibration
with USB6001Thermocouples(device="Dev1") as daq:
    measurement = daq.read()
    print(measurement.tc1_c, measurement.tc2_c, measurement.delta_c)
```

Important: NI-DAQmx is a system-level driver; the Python `nidaqmx` module alone
cannot talk to the USB-6001 if NI-DAQmx is missing.
