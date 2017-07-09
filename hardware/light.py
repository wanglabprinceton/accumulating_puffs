import numpy as np
import logging
from daq import DAQOut, Trigger

class Light(object):
    OFF,ON = 0,1
    def __init__(self, on=True, port='port0/line4', saver=None, val=5.0):
        self.on = on

        if not self.on:
            return 

        self.port = port
        self.saver = saver
        self.daq = DAQOut(DAQOut.DIGITAL_OUT, ports=[self.port])
        self.trig = Trigger([1,1,1,1], dtype=np.uint8)
        self.end_trig = Trigger([0,0,0,0], dtype=np.uint8)

        self.is_on = False
    def _set_on(self):
        if not self.on: # light is not being used
            return

        if self.is_on:
            return
        
        self.daq.trigger(self.trig, clear=False)
        if self.saver:
            self.saver.write('light', dict(state=self.ON))
        self.is_on = True
    def _set_off(self):
        if not self.on: # light is not being used
            return

        if not self.is_on:
            return

        self.daq.trigger(self.end_trig, clear=False)
        if self.saver:
            self.saver.write('light', dict(state=self.OFF))
        self.is_on = False
    def set(self, state):
        if state == 0:
            self._set_off()
        elif state == 1:
            self._set_on()
    def end(self):
        if self.on:
            self.daq.release()
