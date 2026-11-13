
"""Live picoampere plot. Usage: python examples/live_plot.py COM4"""

import argparse
from collections import deque
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from keithley6485 import Keithley6485

p = argparse.ArgumentParser()
p.add_argument('port', nargs='?', default='COM4')
p.add_argument('--baud', type=int, default=9600)
p.add_argument('--interval', type=float, default=0.5)
a = p.parse_args()

meter = Keithley6485(a.port, baud=a.baud)

xs = deque(maxlen=500)
ys = deque(maxlen=500)

fig, ax = plt.subplots()
line, = ax.plot([], [], marker='.', markersize=3)

ax.set_xlabel('Time')
ax.set_ylabel('Current (pA)')
ax.set_title('Keithley 6485 — live current')


def update(_):
    m = meter.read_current()

    xs.append(datetime.fromisoformat(m.timestamp_utc))
    ys.append(m.picoamperes)

    line.set_data(list(xs), list(ys))
    ax.relim()
    ax.autoscale_view()
    fig.autofmt_xdate()

    return (line,)


try:
    meter.connect()
    print(meter.identify())

    anim = FuncAnimation(
        fig,
        update,
        interval=max(100, int(a.interval * 1000)),
        cache_frame_data=False
    )

    plt.show()

finally:
    meter.close()
