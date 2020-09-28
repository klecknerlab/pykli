from kli.thorlabs import KDC101
import time

d = KDC101(0)
# d.identify()
# print(d.get_vel_params(5, 1))
# d.set_vel_params(5, 2.5)
time.sleep(0.05)
print(d.get_vel_params())

p = d.get_pos()
print(p)
# d.move(0.001 if p < 0 else -0.01)
d.move(0, absolute=True)

time.sleep(0.2)

print(d.get_pos())
