
from keithley6485 import Keithley6485

with Keithley6485('COM4') as meter:
    print('Connected:', meter.identify())

    meter.configure_current(
        autorange=True,
        nplc=1
    )

    for measurement in meter.stream(
        interval_s=1,
        count=10
    ):
        print(
            measurement.timestamp_utc,
            f'{measurement.picoamperes:.3f} pA'
        )
