import numpy as np
from util import now
import multiprocessing as mp
import threading

class SICommunicator():
    def __init__(self, *args, **kwargs):
        pass
    def basename(self, *args, **kwargs):
        pass
    def next_file(self, *args, **kwargs):
        pass

class DAQIn(object):
    ANALOG_IN,ANALOG_OUT,DIGITAL_IN,DIGITAL_OUT = 0,0,0,0
    sample_rate = 0
    def __init__(self,*args,**kwargs):
        self.t0 = now()
        self.sample_rate = 40
        self.data_q = mp.Queue()
        self.on = True
        threading.Thread(target=self.go).start()
    def go(self):
        while self.on:
            while now()-self.t0 < 1./self.sample_rate:
                pass
            self.t0 = now()
            dat = (0.1*np.arange(50)).reshape([5,10]).astype(float)+np.random.normal(0,.5,size=[5,10])
            if np.random.random()<0.15:
                dat[0,:] = np.random.choice([4,5,6,7,8])
            if np.random.random()<0.15:
                dat[1,:] = np.random.choice([4,5,6,7,8])
            self.data_q.put( [now(), now(), dat] ) 
    def trigger(self, *args, **kwargs):
        pass
    def release(self):
        self.on = False

class DAQOut(object):
    ANALOG_IN,ANALOG_OUT,DIGITAL_IN,DIGITAL_OUT = 0,0,0,0
    sample_rate = 0
    def __init__(self,*args,**kwargs):
        self.t0 = now()
        self.sample_rate = 40
    def get(self):
        while now()-self.t0 < 1./self.sample_rate:
            pass
        self.t0 = now()
        return now(),(0.1*np.arange(50)).reshape([5,10]).astype(float)+np.random.normal(0,.5,size=[5,10])
    def trigger(self, *args, **kwargs):
        pass
    def release(self):
        pass

class Trigger(object):
    def __init__(*args, **kwargs):
        pass

class _dummy():
    sync_val = mp.Value('i',0)
    
class PSEye(object):
    cS = None
    SAVING = type('obj', (object,), {'value' : None})
    def __init__(self, *args,**kwargs):
        self.flushing = mp.Value('i',0)
        self.pseye = _dummy()
    def start(self):
        pass
    def begin_saving(self):
        pass
    def get_current_frame(*args,**kwargs):
        return np.random.random([320,240])
    def save_on(self):
        pass
    def end(self):
        pass
    def get(self):
        return (255*np.random.random([320,240])).astype(np.uint8)

default_cam_params = dict()
