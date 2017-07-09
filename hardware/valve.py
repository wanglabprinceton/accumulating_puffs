import numpy as np
from scipy.stats import linregress
import logging, threading
from daq import DAQOut, Trigger
from util import now
import time
import config

def reward_scale_to_volume(side, scale):
    dur = config.reward_dur[side] * scale
    sc = config.spout_calibration
    m,i,_,_,_ = linregress(sc['durations'], sc['volumes'])
    return m*dur + i

def calibrate_spout(side, dur, n=25, delay=2.0):
    v = Valve(**config.spout_params)
    #time.sleep(4)
    for i in xrange(n):
        v.go(side, dur)
        time.sleep(delay)
    v.end()
    
def give_reward(side):
    v = Valve(**config.spout_params)
    v.go(side)
    time.sleep(config.spout_params['duration'][side]*1.5)
    v.end()
    
def puff_check():
    v = Valve(ports=['port0/line0','port0/line1'])
    logging.info('Starting test in 5 seconds...')
    time.sleep(4.5)
    for i in xrange(10):
        v.go(0, config.stim_dur)
        time.sleep(0.200)
    time.sleep(1.5)
    for i in xrange(10):
        v.go(1, config.stim_dur)
        time.sleep(0.200)
    v.end()
    
def open_valves():
    v = Valve()
    v._open(0)
    v._open(1)
    v.end()
def close_valves():
    v = Valve()
    v._close(0)
    v._close(1)
    v.end()
    
class Valve(object):
    # used for puff or water valves under digital control
    OPEN,CLOSE = 0,1
    def __init__(self, ports=['port0/line2','port0/line3'], saver=None, duration=[0.1,0.1], name='valve', force_next=True, calibration=None):
        self.ports = ports
        self.duration = duration
        self.saver = saver
        self.name = name
        self.is_open = [False for _ in ports]
        self.force_next = force_next #if a trigger is sent while open, close it and reopen it
        self.nlnr = [0,0]
        self.calibration = calibration
        
        if type(self.duration) in [int, float]:
            self.duration = [self.duration for i in self.ports]

        self.daqs = [DAQOut(DAQOut.DIGITAL_OUT, ports=[port]) for port in self.ports]
        self.trig = Trigger([1,1,1,1], dtype=np.uint8)
        self.end_trig = Trigger([0,0,0,0], dtype=np.uint8)
        self.active = 0
    def get_nlnr(self):
        ret = self.nlnr
        self.nlnr = [0,0]
        return ret
    def _close(self, side):
        self.daqs[side].trigger(self.end_trig, clear=False)
        self.is_open[side] = False
        if self.saver:
            self.saver.write(self.name, dict(side=side, state=self.CLOSE))
    def _open(self, side):
        self.daqs[side].trigger(self.trig, clear=False)
        self.is_open[side] = True
        self.nlnr[side] += 1
        if self.saver:
            self.saver.write(self.name, dict(side=side, state=self.OPEN))

    def go(self, side, dur=None, scale=1.0):
        if dur == None:
            dur = self.duration[int(side)]
        dur = dur * scale
        threading.Thread(target=self.hold_open, args=(int(side),dur)).start()

    def hold_open(self, side, dur):
        self.active += 1
        if self.is_open[side]:
            if self.force_next:
                self._close(side)
            elif not self.force_next:
                return
        start = now()
        self._open(side)
        while now()-start < dur:
            pass
        self._close(side)
        self.active -= 1

    def end(self):
        while self.active != 0:
            pass
        for daq in self.daqs:
            daq.release()
