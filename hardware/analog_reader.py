import time, sys, threading, logging, copy, Queue, warnings
import multiprocessing as mp
import numpy as np
import pylab as pl
from daq import DAQIn
from expts.routines import add_to_saver_buffer
from util import now,now2

class AnalogReader(mp.Process):
    """
    Instantiates a new process that handles a DAQIn object.
    The main thread constantly checks the DAQIn for anything in its data_q, saving it when there, and also making it available to public requests, like the exp interface
    """

    READ_BUF_SIZE = 10
    ACCUM_SIZE = 2000 # Must be multiple of READ_BUF_SIZE

    def __init__(self, ports=['ai0','ai1','ai5','ai6'], portnames=['lickl','lickr','puffl','puffr'], runtime_ports=[0,1], lickport_ports=[0,1], moving_port=2, moving_magnitude=5., lick_thresh=6., holding_thresh=1.0, moving_thresh=1.0, daq_sample_rate=500., save_buffer_size=8000, saver_obj_buffer=None, sync_flag=None, **daq_kwargs):
        super(AnalogReader, self).__init__()
        self.daq_kwargs = daq_kwargs
        
        # Sync
        self.sync_flag = sync_flag
        self.sync_val = mp.Value('d', 0)

        # Data acquisition parameters
        self.ports = ports
        self.portnames = portnames
        self.runtime_ports = runtime_ports # to be used in accumulator and lick/holding variable, and wheel sensor
        self.lickport_ports = lickport_ports # indices *of runtime_ports* that correspond to lick tubes
        self.moving_port = moving_port # index *of runtime_ports* that corresponds to wheel sensor
        self._lickport_idxs = np.asarray(self.runtime_ports)[self.lickport_ports]
        self.daq_sample_rate = daq_sample_rate
        
        # Data processing parameters
        self.thresh = lick_thresh
        self.holding_thresh = int(holding_thresh * self.daq_sample_rate)
        self.moving_thresh = int(moving_thresh * self.daq_sample_rate)
        self.moving_magnitude = moving_magnitude

        # data containers
        self.accum = np.zeros((len(self.ports),self.ACCUM_SIZE))
        self.accum_ts = []
        self.accum_q = mp.Array('d', len(self.runtime_ports)*self.ACCUM_SIZE)

        # processing containers
        self.licked_ = mp.Array('b', [False, False])
        self.holding_ = mp.Value('b', False)
        self.moving_ = mp.Value('b', False)
        
        # threading structures
        self.logic_lock = mp.Lock()

        # saving
        self._saving = mp.Value('b', False)
        self.save_buffer_size = save_buffer_size
        self.n_added_to_save_buffer = 0
        self.save_buffer = np.zeros([len(self.ports),self.save_buffer_size])
        self.save_buffer_ts = np.zeros([2,self.save_buffer_size])
        self.saver_obj_buffer = saver_obj_buffer

        self._on = mp.Value('b', True)
        self._kill_flag = mp.Value('b', False)
        self.start()

    @property
    def licked(self):
        with self.logic_lock:
            temp = mp.sharedctypes.copy(self.licked_.get_obj())
            self.licked_[:] = [False, False]
        return temp
    @property
    def holding(self):
        with self.logic_lock:
            temp = self.holding_.value
            self.holding_.value = False
        return temp
    @property
    def moving(self):
        if self.moving_port is None:
            return None
        with self.logic_lock:
            temp = self.moving_.value
            self.moving_.value = False
        return temp

    def run(self):
        while not self.sync_flag.value:
            self.sync_val.value = now()

        self.daq = DAQIn(ports=self.ports, read_buffer_size=self.READ_BUF_SIZE, sample_rate=self.daq_sample_rate, **self.daq_kwargs)
        
        while self._on.value:
            
            if self._kill_flag.value:
                self.daq.release()

            try:
                ts,ts2,dat = self.daq.data_q.get(timeout=0.5)
            except Queue.Empty:
            
                if self._kill_flag.value:
                   # final dump:
                    if self.n_added_to_save_buffer:
                        add_to_saver_buffer(self.saver_obj_buffer, 'analogreader', self.save_buffer[:,-self.n_added_to_save_buffer:].T.copy(), ts=self.save_buffer_ts[0,-self.n_added_to_save_buffer:].copy(), ts2=self.save_buffer_ts[1,-self.n_added_to_save_buffer:].copy(), columns=self.portnames)
                    self._on.value = False
                    
                continue

            if self._kill_flag.value:
                logging.info('Analogreader final flush: {} reads remain.'.format(self.daq.data_q.qsize()))

            dat = dat.reshape((len(self.ports),self.READ_BUF_SIZE))
            
            # update save buffer with new data
            self.save_buffer = np.roll(self.save_buffer, -self.READ_BUF_SIZE, axis=1)
            self.save_buffer_ts = np.roll(self.save_buffer_ts, -self.READ_BUF_SIZE, axis=1)
            self.save_buffer[:,-self.READ_BUF_SIZE:] = dat[:,:]
            self.save_buffer_ts[:,-self.READ_BUF_SIZE:] = np.array([ts,ts2])[:,None]
            if self._saving.value:
                self.n_added_to_save_buffer += self.READ_BUF_SIZE
                dump = self.n_added_to_save_buffer >= self.save_buffer_size
            else:
                dump = False

            # update accumulator (runtime analysis buffer)
            self.accum = np.roll(self.accum, -self.READ_BUF_SIZE, axis=1)
            self.accum[:,-self.READ_BUF_SIZE:] = dat[:,:]
            self.accum_ts += [ts]*self.READ_BUF_SIZE
            self.accum_q[:] = (self.accum.copy()[self.runtime_ports]).ravel()
            
            # update experimental logic
            with self.logic_lock:
                
                self.licked_[:] = np.any(dat[self._lickport_idxs,:]>=self.thresh, axis=1)
                self.holding_.value = np.any(np.all(self.accum[self._lickport_idxs,-self.holding_thresh:]>self.thresh, axis=1))
                if self.moving_port is not None:
                    _tmp_moving = self.accum[self.runtime_ports[self.moving_port], -self.moving_thresh:]
                    self.moving_.value = np.max(_tmp_moving)-np.min(_tmp_moving) > self.moving_magnitude

            if dump and self._saving.value:
                if self.n_added_to_save_buffer > self.save_buffer_size:
                    warnings.warn('DAQ save buffer size larger than expected: some samples were missed. Size={}, Expected={}'.format(self.n_added_to_save_buffer,self.save_buffer_size))
                add_to_saver_buffer(self.saver_obj_buffer, 'analogreader', self.save_buffer.T.copy(), ts=self.save_buffer_ts[0,:].copy(), ts2=self.save_buffer_ts[1,:].copy(), columns=self.portnames)
                self.n_added_to_save_buffer = 0
    
    def get_accum(self):
        return np.frombuffer(self.accum_q.get_obj()).reshape([len(self.runtime_ports), self.ACCUM_SIZE])
    
    def begin_saving(self):
        self.n_added_to_save_buffer = 0
        self._saving.value = True

    def end(self):
        self._kill_flag.value = True
        while self._on.value:
            pass

if __name__ == '__main__':
    pl.figure()
    lr = AnalogReader()
    lr.start()
    show_lines = pl.plot(lr.accum.T)
    pl.ylim([-.1,10.1])
    while True:
        for idx,sl in enumerate(show_lines):
            sl.set_ydata(lr.accum[idx])
        pl.draw()
        pl.pause(0.001)
