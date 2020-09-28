#!/usr/bin/python3
#
# Copyright 2020 Dustin Kleckner
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import struct
import platform
import time

if platform.system() == 'Windows':
    USE_SERIAL = True
    import serial
else:
    USE_SERIAL = False
    from pyftdi import ftdi
    import usb.core

# word -> H
# short -> h
# dword -> I
# long -> i

class AptDevice:
    '''A generic Thorlabs Apt/Kinesis device.

    This is a base class which provides a cross-platform interface to these
    devices.

    On Windows machines, pyserial is used to communicate with the devices; to
    use this, you need to enable serial communication in the windows drivers
    (which can be accessed in Device Manager; the devices will appear under
    the generic USB devices listing.)

    On Mac (and probably Linux, but this is untested), the devices are accessed
    using the pyftdi library.

    Parameters
    ----------
    device : int or string (default: 0)
        On Windows, this should be the comport as a string (e.g. ``"COM5"``).
        On other systems, this is the index to the first device which matches
        the product ID.  Unless you have multiple of the same type of device,
        you can leave this as the default.
    '''
    USB_MANUFACTURER = "Thorlabs"
    USB_PRODUCT_NAME = None

    def __init__(self, device=0, timeout=0.5):
        if USE_SERIAL:
            if device == 0:
                raise ValueError("On Windows machines, initiate device with a COM port.  (e.g. 'COM5')")

            self.port = serial.Serial(port=port, baudrate=115200, stopbits=1, timeout=timeout)
            self._write = self.port.write
            self._read = self.port.read

            time.sleep(0.05)
            self.port.reset_input_buffer()
            self.port.reset_output_buffer()
            time.sleep(0.05)

            self._flush = port.flush()

        else:
            if self.USB_PRODUCT_NAME:
                devs = usb.core.find(find_all=True, manufacturer=self.USB_MANUFACTURER, product=self.USB_PRODUCT_NAME)
            else:
                devs = usb.core.find(find_all=True, manufacturer=self.USB_MANUFACTURER)

            devs = list(devs)
            # print(devs)

            if not devs:
                raise ValueError('USB device not found -- is it connected?')
            if device >= len(devs):
                raise ValueError('Requested index (%d) is more than available devices (found %d)' % (device, len(devs)))

            self.port = ftdi.Ftdi()
            self.port.open_from_device(devs[device])
            self.port.set_baudrate(115200)
            self.port.set_line_property(8, 1, "N")

            time.sleep(0.05)
            self.port.purge_buffers()
            time.sleep(0.05)

            self.port.set_flowctrl('hw')
            self.port.set_rts(True)
            self._write = self.port.write_data
            self._read = self.port.read_data

            self._flush = self.port.purge_buffers


    def close(self):
        '''Close the port manually.'''
        if hasattr(self, 'port'):
            self.port.close()
            del self.port, self._write, self._read


    def __del__(self):
        self.close()

    def _write_packet(self, cmd, param1=0, param2=0, data=None, dest=0x50, src=0x01):
        if data is None:
            self._write(struct.pack('<H4B', cmd, param1, param2, dest, src))
        elif data is not None:
            self._write(struct.pack('<2H2B', cmd, len(data), dest | 0x80, src))
            self._write(data)
        else:
            raise ValueError('_write_packet should specify either param1 and param2 or a data packet')

        # self.port.flush()

    def _read_packet(self):
        header = self._read(6)
        # print(f'{header}')
        if len(header) != 6: return None

        result = {'cmd': struct.unpack('<H', header[0:2])[0], 'source': header[5], 'id': header[0:1]}

        if header[4] & 0x80: #This indicates a data packet is attached
            result['dest'] = header[4] & 0x7F
            packet_length, = struct.unpack('<H', header[2:4])
            result['data'] = self._read(packet_length)

        else:
            result['dest'] = header[4]
            result['param1'] = header[2]
            result['param2'] = header[3]

        return result

    def _get_packet(self, cmd, attempts=10, wait=0.05):
        for n in range(attempts):
            packet = self._read_packet()
            if packet is not None and packet.get('cmd', None) == cmd:
                return packet

            time.sleep(wait)

        raise ValueError(f'Expected packet with command 0x{cmd:02x}, did not receive in {attempts} attempts')


    def identify(self):
        '''Flash the front panel controls to identify the device.'''
        self._write_packet(0x0223, 0, 0)


    def info(self):
        '''Returns an information dictionary about the device.'''
        self._write_packet(0x0005, 0, 0)
        data = struct.unpack('<L8sH4B48s12sHHH', self._get_packet(0x006)['data'])

        return {
            'serial': data[0],
            'model': data[1],
            'type': data[2],
            'firmware': data[3:7],
            'notes': data[7],
            'hw_version': data[9],
            'mod_state': data[10],
            'num_channels': data[11]
        }


class TPZ001(AptDevice):
    '''A driver for a Thorlabs TPZ001 Piezo Driver.

    Parameters
    ----------
    device : int or string (default: 0)
        On Windows, this should be the comport as a string (e.g. ``"COM5"``).
        On other systems, this is the index to the first device which matches
        the product ID.  Unless you have multiple of the same type of device,
        you can leave this as the default.
    '''

    USB_MANUFACTURER = "Thorlabs"
    USB_PRODUCT_NAME = None

    def set_PI(self, P, I):
        '''Set the proportional/integral constant for the feedback loop.

        Parameters
        ----------
        P : int
            The proportional constant (defaults to 100 in the device)
        I : int
            The integral constant (defaults to 20 in the device)
        '''
        self.identify()
        self._write_packet(0x0655, data=struct.pack('<3H', 1, P, I))

    def get_PI(self):
        '''Get the current proportional/integral constant for the feedback
        loop.

        Returns
        -------
        P : int
        I : int
        '''
        self._write_packet(0x065B, 1, 0)
        channel, P, I = struct.unpack('<3H', self._get_packet(0x065C)['data'][:6])
        return P, I

    def set_control_mode(self, closed, smooth=False):
        '''Sets the control mode.

        Parameters
        ----------
        closed : bool
            If True, operate in closed loop mode

        Keywords
        --------
        smooth : bool (default: False)
            If True, changes modes in a smooth fashion to prevent jolts.
            (untested!)
        '''
        mode = (2 if closed else 1)
        if smooth: mode += 2
        self._write_packet(0x0640, 1, mode)

    def set_volts(self, V):
        '''Set the output voltage in open loop mode.  Note: command ignored in
        closed loop mode!

        Parameters
        ----------
        V : float
            The output in volts.  Will raise an error if outside range.
        '''
        if not hasattr(self, 'max_volts'):
            self.max_volts = self.get_settings()['V_lim']
        if (V < 0) or (V > self.max_volts):
            raise ValueError('V must be between 0 and max_volts (%d)' % self.max_volts)

        self._write_packet(0x0643, data=struct.pack('<2H', 1, int((V / self.max_volts) * 32767 + 0.5)))

    def set_pos(self, pos):
        '''Set the output position in closed loop mode.  Note: command ignored
        in open loop mode!

        Parameters
        ----------
        pos : float (0-100)
            The output in % of maximum.  Will raise an error if outside range.
        '''
        if (pos < 0) or (pos > 100):
            raise ValueError('pos must be between 0 and 100')

        self._write_packet(0x0646, data=struct.pack('<2H', 1, int((pos / 100) * 65535 + 0.5)))


    def get_settings(self):
        '''Get the information on the current settings (voltage limit and
        analog input settings).
        '''
        self._write_packet(0x07D5, 1, 0)
        channel, V_lim, analog_in = struct.unpack('<3H', self._get_packet(0x07D6)['data'][:6])
        return {
            'V_lim': {1:75, 2:100, 3:150}[V_lim],
            'analog_input': {1:'A', 2:'B', 3:'SMA'}[analog_in]
        }


# word -> H
# short -> h
# dword -> I
# long -> i


class KDC101(AptDevice):
    USB_MANUFACTURER = "FTDI"
    USB_PRODUCT_NAME = "Kinesis K-Cube  DC Driver"
    DRIVER_T = 2048/6E6

    def __init__(self, *args, **kwargs):
        self.set_counts_per_unit(kwargs.pop('counts_per_unit', 34304))
        super().__init__(*args, **kwargs)


    def set_counts_per_unit(self, counts):
        self._x_conv = counts
        self._v_conv = counts * self.DRIVER_T * 65536
        self._a_conv = self._v_conv * self.DRIVER_T

    # This doesn't work -- I think this stage doesn't use this commmand!
    #
    # def get_stage_params(self, channel=1):
    #     '''Returns an information dictionary about the stage axis.
    #
    #     Note: this is called on initialization, and the results are available
    #     in the `stage_info` attribute.
    #
    #     Keywords
    #     --------
    #     channel : int (default: 1)
    #
    #     '''
    #     self._write_packet(0x04F1, 1)
    #     data = struct.unpack('<HHH16sII5i4H4I', self._get_packet(0x04F2)['data'])
    #
    #     return {
    #         'stage_id': data[1],
    #         'axis_id': data[2],
    #         'part_no_axis': data[3],
    #         'serial': data[4],
    #         'counts_per_unit': data[5],
    #         'min_pos': data[6],
    #         'max_pos': data[7],
    #         'max_accel': data[8],
    #         'max_deccel': data[9],
    #         'max_vel': data[10]
    #     }

    # My driver does not appear to send a move complete message!
    # def move(self, distance, channel=1, absolute=False, wait=False, wait_time=5, wait_checks=100):
    def move(self, distance, channel=1, absolute=False):
        '''Move the stage.

        Parameters
        ----------
        distance : float
            The distance to move (unless absolute=True, in which case this is
            the position to move to).  The units are either mm (linear stages)
            or degrees (rotation stages).

        Keywords
        --------
        channel : int (default: 1)
        absolute : int (default: False)
            If True, position is an absolute coordinate (otherwise its a
            relative move).
        '''
        #
        # wait : int (default: False)
        #     If True, command waits for
        # wait_time : float (default: 5)
        #     Total time to wait for a motor complete message
        # wait_checks : int (default: 100)
        #     The number of times the complete message is checked for.  If it
        #     fails to receive a message in this time, it will raise an error.

        d = int(distance * self._x_conv + 0.5)
        print(d)

        if absolute:
            self._write_packet(0x0453, data=struct.pack('<Hi', channel, d))
        else:
            self._write_packet(0x0448, data=struct.pack('<Hi', channel, d))

        # if wait:
        #     self.wait_for_move(channel=channel, wait_time=wait_time, wait_checks=wait_checks)

    # def wait_for_move(self, channel=1, wait_time=5, wait_checks=100):
    #     '''Wait for a move completion command to be sent.
    #
    #     Keywords
    #     -------
    #     channel : int (default: 1)
    #         The channel to wait for.
    #     wait_time : float (default: 5)
    #         Total time to wait for a motor complete message
    #     wait_checks : int (default: 100)
    #         The number of times the complete message is checked for.  If it
    #         fails to receive a message in this time, it will raise an error.
    #
    #     '''
    #
    #     for n in range(wait_checks):
    #         time.sleep(wait_time/wait_checks)
    #         print(self._read(6))
    #         packet = self._read_packet()
    #
    #         # print('.' if packet is None else packet['cmd'])
    #         if packet is not None and packet.get('cmd', None) == 0x0464 and packet.get('param1', None) == channel:
    #             return packet['param1']
    #     else:
    #         raise RuntimeError(f'move did not comlete in {wait_time} s; increase wait time?')

    def get_vel_params(self, channel=1):
        '''Get the current velocity parameters of the stage.

        Note that the velocities and accelerations are converted to units/s or
        units/s^2.  (units = mm or deg, depending on if it's a linear or
        rotation stage)

        Keywords
        --------
        channel : int (default: 1)

        Returns
        -------
        info : dictionary
            A dictionary with the parameters.  Velocities and accelerations are
            converted to the base units (mm or deg)
        '''

        self._flush() #Clear the input buffer, in case there are uncaught move commands
        self._write_packet(0x0414, channel)
        data = struct.unpack('<Hiii', self._get_packet(0x0415)['data'])

        return {
            'channel': data[0],
            'min_vel': data[1] / self._v_conv,
            'accel': data[2] / self._a_conv,
            'max_vel': data[3] / self._v_conv,
        }

    def set_vel_params(self, accel, max_vel, channel=1, min_vel=0):
        '''Get the current velocity parameters of the stage.

        Parameters
        ----------
        accel : float
            The acceleration in units^2/s
        max_vel : float
            The maximum velocity in units/s

        Keywords
        --------
        channel : int (default: 1)
        min_vel : int (default: 0)
            The minimum velocity.  Typically left at 0.
        '''

        mv = int(min_vel * self._v_conv + 0.5)
        a = int(accel * self._a_conv + 0.5)
        Mv = int(max_vel * self._v_conv + 0.5)

        self._write_packet(0x0413, data=struct.pack('<H3i', channel, mv, a, Mv))


    def get_jog_params(self, channel=1):
        '''Get the current jog parameters of the stage.

        Note that the velocities and accelerations are converted to units/s or
        units/s^2.  (units = mm or deg, depending on if it's a linear or
        rotation stage)

        Keywords
        --------
        channel : int (default: 1)

        Returns
        -------
        info : dictionary
            A dictionary with the parameters.  Velocities and accelerations are
            converted to the base units (mm or deg)
        '''

        self._flush() #Clear the input buffer, in case there are uncaught move commands
        self._write_packet(0x0417, channel)
        data = struct.unpack('<2HiiiiH', self._get_packet(0x0418)['data'])

        return {
            'channel': data[0],
            'jog_mode': {1:'continuous', 2:'single step'}.get(data[1], data[1]),
            'step_size': data[2] / self._x_conv,
            'min_vel': data[3] / self._v_conv,
            'accel': data[4] / self._a_conv,
            'max_vel': data[5] / self._v_conv,
            'stop_mode': {1:'immediate', 2:'profiled'}.get(data[6], data[6]),
        }

    # def get_pot_params(self, channel=1):
    #     '''Get the current rotary dial parameters of the controller.
    #
    #     Note that the velocities and accelerations are converted to units/s or
    #     units/s^2.  (units = mm or deg, depending on if it's a linear or
    #     rotation stage)
    #
    #     Keywords
    #     --------
    #     channel : int (default: 1)
    #
    #     Returns
    #     -------
    #     info : dictionary
    #         A dictionary with the parameters.  Velocities and accelerations are
    #         converted to the base units (mm or deg)
    #     '''
    #
    #     self._write_packet(0x04B1, 1)
    #     data = struct.unpack('<2HiHiHiHi', self._get_packet(0x04B2)['data'])
    #
    #     return {
    #         'channel': data[0],
    #         'wnd0': data[1],
    #         'vel1': data[2],
    #         'wnd1': data[3],
    #         'vel2': data[4],
    #         'wnd2': data[5],
    #         'vel3': data[6],
    #         'wnd3': data[7],
    #         'vel4': data[8]
    #     }


    def get_pos(self, channel=1):
        '''Get the current position of the stage.

        Keywords
        --------
        channel : int (default: 1)

        Returns
        -------
        position : float
            The position in base units (mm or deg)
        '''

        self._flush() #Clear the input buffer, in case there are uncaught move commands
        self._write_packet(0x0411, channel)
        data = struct.unpack('<Hi', self._get_packet(0x0412)['data'])

        return data[1] / self._x_conv
