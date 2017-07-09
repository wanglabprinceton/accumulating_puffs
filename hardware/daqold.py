from config import TESTING_MODE

if TESTING_MODE:
    from dummy import DAQ, Trigger

elif not TESTING_MODE:
    import PyDAQmx as pydaq
    from PyDAQmx.DAQmxCallBack import *
    import numpy as np
    import warnings, threading, logging, copy
    from util import now

    class List(list):
        pass

    class Trigger(object):
        def __init__(self, msg=[], duration=None, name='noname', dtype=np.float64):
            self.duration = duration
            self.dtype = dtype
            self._msg = None
            self.msg = msg
            self.name = name

        @property
        def msg(self):
            return self._msg
        @msg.setter
        def msg(self, msg):
            self._msg = np.array(msg).astype(self.dtype)

        def metadata(self):
            md = {}
            md['duration'] = self.duration
            md['msg'] = str(self.msg)
            md['name'] = self.name
            return md

    class DAQ(pydaq.Task):
        ANALOG_OUT = 0
        DIGITAL_OUT = 1
        ANALOG_IN = 2
        DIGITAL_IN = 3
        def __init__(self, mode, device='Dev1', ports=['ao0'], portlabels=['none'], analog_minmax=(-10,10), read_buffer_size=10, timeout=5., sample_rate=400., AI_mode=pydaq.DAQmx_Val_Diff, save_buffer_size=8000, saver=None, saver_name='daq'):
            # example digital port: 'Port1/Line0:3'
            # example analog port: 'ao0'
            # DAQ properties
            pydaq.Task.__init__(self)
            self.mode = mode
            self.device = device
            self.port_names = ports
            self.port_labels = portlabels
            self.ports = ['/'.join([self.device,port]) for port in self.port_names]
            self.timeout = timeout
            self.sample_rate = sample_rate
            self.read = pydaq.int32()
            self.AI_mode = AI_mode

            self.last_ts = None

            # Trigger properties
            self.minn,self.maxx = analog_minmax
            if self.mode == self.ANALOG_OUT:
                self.clear_trig = Trigger(msg=[self.minn for _ in self.ports])
            elif self.mode == self.DIGITAL_OUT:
                self.clear_trig = Trigger(msg=[0,0,0,0], dtype=np.uint8)

            # params & data
            self.read_buffer_size = read_buffer_size
            self.effective_buffer_size = self.read_buffer_size * len(self.ports)
            self.read_data = np.zeros(self.effective_buffer_size)
            
            # Saving
            self.saver = saver
            self.SAVING = False
            self.save_buffer_size = save_buffer_size
            self.n_added_to_save_buffer = 0
            self.save_buffer = np.zeros([len(self.ports),self.save_buffer_size])
            self.save_buffer_ts = np.zeros(self.save_buffer_size)
            self.save_lock = threading.Lock()
            self.saver_name = saver_name
            
            # Setup task
            try:
                if self.mode == self.DIGITAL_OUT:
                    for port in self.ports:
                        self.CreateDOChan(port, "OutputOnly", pydaq.DAQmx_Val_ChanForAllLines)

                elif self.mode == self.ANALOG_OUT:
                    for port in self.ports:
                        self.CreateAOVoltageChan(port, '', self.minn, self.maxx, pydaq.DAQmx_Val_Volts, None)

                elif self.mode == self.ANALOG_IN:
                    self.CreateAIVoltageChan(','.join(self.ports), '', self.AI_mode, self.minn, self.maxx, pydaq.DAQmx_Val_Volts, None)
                    self.CfgSampClkTiming('', self.sample_rate, pydaq.DAQmx_Val_Rising, pydaq.DAQmx_Val_ContSamps, self.read_buffer_size)
                    self.AutoRegisterEveryNSamplesEvent(pydaq.DAQmx_Val_Acquired_Into_Buffer, self.read_buffer_size, 0)
                    self.AutoRegisterDoneEvent(0)
            
                    self._data_lock = threading.Lock()
                    self._newdata_event = threading.Event()
                
                self.StartTask()
            except:
                warnings.warn("DAQ task did not successfully initialize")
                raise

        def EveryNCallback(self):
            with self._data_lock:
                self.last_ts = now()
                self.ReadAnalogF64(self.read_buffer_size, self.timeout, pydaq.DAQmx_Val_GroupByChannel, self.read_data, self.effective_buffer_size, pydaq.byref(self.read), None)
                self._newdata_event.set()
            self.save()
            return 0

        def save(self):
            with self._data_lock:
                ret = self.read_data.copy()
                ts = self.last_ts
            ret = ret.reshape((len(self.ports),self.read_buffer_size))
            assert ret.shape[-1] == self.read_buffer_size

            with self.save_lock:
                self.save_buffer = np.roll(self.save_buffer, -self.read_buffer_size, axis=1)
                self.save_buffer_ts = np.roll(self.save_buffer_ts, -self.read_buffer_size)
                self.save_buffer[:,-self.read_buffer_size:] = ret[:,:]
                self.save_buffer_ts[-self.read_buffer_size:] = ts
                self.n_added_to_save_buffer += self.read_buffer_size
                dump = self.n_added_to_save_buffer >= self.save_buffer_size

                if dump:
                    if self.n_added_to_save_buffer > self.save_buffer_size:
                        logging.error('DAQ save buffer size larger than expected: some samples were missed. Size={}, Expected={}'.format(self.n_added_to_save_buffer,self.save_buffer_size))
                    if self.SAVING and self.saver:
                        self.saver.write(self.saver_name, self.save_buffer.T.copy(), ts=self.save_buffer_ts.copy(), columns=self.port_labels)
                    self.n_added_to_save_buffer = 0

        def trigger(self, trig, clear=None):
            if clear == None:
                clear = self.clear_trig
            try:
                if self.mode == self.DIGITAL_OUT:
                    self.WriteDigitalLines(1,1,self.timeout,pydaq.DAQmx_Val_GroupByChannel,trig.msg,None,None)
                    if clear is not False:
                        self.WriteDigitalLines(1,1,self.timeout,pydaq.DAQmx_Val_GroupByChannel,clear.msg,None,None)

                elif self.mode == self.ANALOG_OUT:
                    self.WriteAnalogF64(1,1,self.timeout,pydaq.DAQmx_Val_GroupByChannel,trig.msg,None,None)
                    if clear is not False:
                        self.WriteAnalogF64(1,1,self.timeout,pydaq.DAQmx_Val_GroupByChannel,clear.msg,None,None)
            except:
                logging.warning("DAQ task not functional. Attempted to write %s."%str(trig.msg))
                raise

        def get(self, blocking=True, timeout=1.e10):
            if blocking:
                if not self._newdata_event.wait(timeout):
                    raise ValueError("timeout waiting for data from device")
            with self._data_lock:
                self._newdata_event.clear()
                ret = self.read_data.copy()
                ts = self.last_ts
            ret = ret.reshape((len(self.ports),self.read_buffer_size))
            return (ts,ret)

        def release(self):
            try:
                self.StopTask()
                self.ClearTask()
            except:
                pass
                
if __name__ == '__main__':
    import pylab as pl
    pl.figure()
    rbf = 10
    d = DAQ(DAQ.ANALOG_IN, ports=['ai0','ai1'], read_buffer_size=rbf)
    data = np.zeros((2,1000))
    show_line1,show_line2 = pl.plot(data.T)
    pl.ylim([-10.1,10.1])
    while True:
        nd = d.get()
        data = np.roll(data, -rbf, axis=1)
        data[:,-rbf:] = nd
        show_line1.set_ydata(data[0])
        show_line2.set_ydata(data[1])
        pl.draw()
        pl.pause(0.001)
            
