from kli.fpga import Synchronizer, reset_fpga
import numpy as np
import time

sync = Synchronizer()
sync.stop()

f0 = 85
step = 1
subdiv = 1000
ticks = 48000000

t = np.arange(0, subdiv) / subdiv
x = np.sin(2 * np.pi * t)
sync.analog_write(0, x)
sync.digital_setup(0, active=True)
sync.digital_setup(1, active=True)

for n in range(20):
    pn = n % 2
    f = f0 + step * n

    base = int(ticks / (f * subdiv) + 0.5)
    print(f'f: {f:.3f} Hz, actual: {ticks/(subdiv*base):.3f} Hz, base ticks: {base:d}')

    cycle = base * subdiv

    sync.pulse_setup(0, pn, 4, 0, cycle//8, cycle//8)
    sync.pulse_setup(1, pn, 10, 0, cycle//20, cycle//20)
    sync.select_program(pn)

    sync.analog_setup(False, True, 0, base)
    sync.cycle_setup(cycle)
    sync.update()
    sync.start()
    time.sleep(1)
