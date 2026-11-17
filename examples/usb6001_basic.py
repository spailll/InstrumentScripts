
"""Example: integrate two thermocouples into another instrument script."""
from usb6001 import USB6001Thermocouples, SensorCalibration

with USB6001Thermocouples(
    device="Dev1",
    calibrations=(SensorCalibration(reference_volts=0.0), SensorCalibration(reference_volts=0.0)),
) as thermocouples:
    m = thermocouples.read()
    print(f"Plate: {m.tc1_c:.2f} °C | Ambient: {m.tc2_c:.2f} °C | Delta: {m.delta_c:.2f} °C")
