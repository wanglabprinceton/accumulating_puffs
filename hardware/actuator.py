import struct, warnings
import ctypes as C
from ctypes.wintypes import DWORD, HANDLE
import numpy as np

# Note that mpusbabi.dll should be located in the same directory as this file
LIB = 'mpusbapi.dll' 

class LActuator():
    def __init__(self, vidpid=r'vid_04d8&pid_fc5f', pos_retracted=0.05, pos_extended=0.95, accuracy=.01, speed=0.5, saver=None):

        self.saver = saver
    
        # load DLL
        self.dll = C.cdll.LoadLibrary(LIB)

        # specify data types for relevant functions
        self.dll._MPUSBOpen.argtypes = [DWORD, C.c_char_p, C.c_char_p, DWORD, DWORD]
        self.dll._MPUSBOpen.restype = HANDLE
        self.dll._MPUSBWrite.argtypes = [HANDLE, C.c_void_p, DWORD, C.c_void_p, DWORD]
        self.dll._MPUSBWrite.restype = DWORD
        self.dll._MPUSBRead.argtypes = [HANDLE, C.c_void_p, DWORD, C.c_void_p, DWORD]
        self.dll._MPUSBRead.restype = DWORD

        _vidpid = C.create_string_buffer(vidpid)
        pep = C.create_string_buffer('\\MCHP_EP1')

        assert self.dll._MPUSBGetDeviceCount(_vidpid)==1, 'Did not detect linear actuator at address {}'.format(vidpid)

        self.handle_out = self.dll._MPUSBOpen(0, _vidpid, pep, 0, 0)
        #self.handle_in = self.dll._MPUSBOpen(0, _vidpid, pep, 1, 0)

        self.set_accuracy(accuracy)
        self.set_speed(speed)
        #self.set_proportional_gain(1) # not sure this works and default is 1 anyway

        self.pos_retracted = pos_retracted
        self.pos_extended = pos_extended

    def _usb_write(self, buf, timeout=1000):
        """Runs a generic usb write command
        buf is a 3-item list of single bytes
        """
        
        timeout = DWORD(timeout)
        n = DWORD(3)

        buftyp = C.c_ubyte * 3
        buf = buftyp(*buf)
        
        # feedback memory, a formality
        l = DWORD(0)
        ptr = C.pointer(l)
        
        res = self.dll._MPUSBWrite(self.handle_out, buf, n, ptr, timeout)
        if res != 1:
            warnings.warn('Actuator did not properly send command. Attempting to re-init...')
            self.end()
            self.__init__()

    def set_accuracy(self, acc):
        # acc is the tolerance as fraction of total stroke

        assert acc>=0. and acc<=1.

        # specify accuracy in API format
        acc = int(np.round(1023 * acc))
        acc_ = struct.pack('<H', acc)
        
        # build 3-byte buffer for API
        buf = [None,None,None]
        buf[0] = 0x01
        buf[1] = struct.unpack('B',acc_[0])[0]
        buf[2] = struct.unpack('B',acc_[1])[0]

        self._usb_write(buf)
        
    def set_speed(self, speed):
        # speed as fraction of max
        
        assert speed>=0. and speed<=1.

        # specify speed in API format
        speed = int(np.round(1023 * speed))
        speed_ = struct.pack('<H', speed)
        
        # build 3-byte buffer for API
        buf = [None,None,None]
        buf[0] = 0x21
        buf[1] = struct.unpack('B',speed_[0])[0]
        buf[2] = struct.unpack('B',speed_[1])[0]

        self._usb_write(buf)

        
    def set_proportional_gain(self, g=1):
        # should be = 1

        # specify accuracy in API format
        g = int(np.round(g))
        g_ = struct.pack('<H', g)
        
        # build 3-byte buffer for API
        buf = [None,None,None]
        buf[0] = 0x0C
        buf[1] = struct.unpack('B',g_[0])[0]
        buf[2] = struct.unpack('B',g_[1])[0]

        self._usb_write(buf)
        

    def goto(self, pos):
        """Position is specified as a float from 0-1, where 0 is retracted and 1 is extended
        In practice, values are enforced to be between 0.05 and 0.95 to increase lifetime of actuator. (never hits physical endstops)
        """
        assert pos>=0.05 and pos<=0.95, 'LActuator goto() accepts a float from 0.05-0.95 for position parameter.'

        # specify position in API format
        pos = int(np.round(1023 * pos))
        pos_ = struct.pack('<H', pos)

        # build 3-byte buffer for API
        buf = [None,None,None]
        buf[0] = 0x20
        buf[1] = struct.unpack('B',pos_[0])[0]
        buf[2] = struct.unpack('B',pos_[1])[0]

        self._usb_write(buf)

    def retract(self):
        if self.saver:
            self.saver.write('actuator', dict(state=0))
        self.goto(self.pos_retracted)
    def extend(self):
        if self.saver:
            self.saver.write('actuator', dict(state=1))
        self.goto(self.pos_extended)

    def end(self):
        self.dll._MPUSBClose(self.handle_out)
        #self.dll._MPUSBClose(self.handle_in)

