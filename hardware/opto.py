import numpy as np
import logging, threading
from daq import DAQOut, Trigger
from util import now
import time

class Opto(object):
    # used for digital control of an opto device
    OFF,ON = 0,1
    def __init__(self, on=True, port='port0/line5', saver=None, name='opto'):
        self.on = on

        if not self.on:
            self.daq = None
            return

        self.port = port
        self.saver = saver
        self.name = name

        self.daq = DAQOut(DAQOut.DIGITAL_OUT, ports=[self.port])
        self.trig = Trigger([1,1,1,1], dtype=np.uint8)
        self.end_trig = Trigger([0,0,0,0], dtype=np.uint8)
        self.trigs = {self.ON:self.trig, self.OFF:self.end_trig}

        self.state = self.OFF

    def _switch(self, state):
        if (not self.on) or (self.daq is None):
            return

        if self.state == state:
            return
        self.daq.trigger(self.trigs[state], clear=False)
        self.state = state
        if self.saver:
            self.saver.write(self.name, dict(state=self.state))

    def set(self, state):
        # on or off, 1 or 0
        self._switch(state)
    
    def end(self):
        if self.daq is not None:
            self.daq.release()
