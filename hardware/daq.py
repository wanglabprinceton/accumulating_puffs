from config import TESTING_MODE

if TESTING_MODE:
    from dummy import DAQIn, DAQOut, Trigger

elif not TESTING_MODE:
    import PyDAQmx as pydaq
    from PyDAQmx.DAQmxCallBack import *
    import numpy as np
    import multiprocessing as mp
    import warnings, threading, logging, copy
    from util import now,now2

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

    class DAQOut(pydaq.Task):
        ANALOG_OUT = 0
        DIGITAL_OUT = 1
        def __init__(self, mode, device='Dev1', ports=['port0/line2','port0/line3'], timeout=5.0, analog_minmax=(-10,10)):
            
            # DAQ properties
            pydaq.Task.__init__(self)
            self.mode = mode
            self.device = device
            self.ports = ports
            self.timeout = timeout
            self.ports = ['/'.join([self.device,port]) for port in self.ports]

            # Trigger properties
            self.minn,self.maxx = analog_minmax
            if self.mode == self.ANALOG_OUT:
                self.clear_trig = Trigger(msg=[self.minn for _ in self.ports])
            elif self.mode == self.DIGITAL_OUT:
                self.clear_trig = Trigger(msg=[0,0,0,0], dtype=np.uint8)
            
            # Setup task
            try:
                if self.mode == self.DIGITAL_OUT:
                    for port in self.ports:
                        self.CreateDOChan(port, "OutputOnly", pydaq.DAQmx_Val_ChanForAllLines)

                elif self.mode == self.ANALOG_OUT:
                    for port in self.ports:
                        self.CreateAOVoltageChan(port, '', self.minn, self.maxx, pydaq.DAQmx_Val_Volts, None)

                self.StartTask()
            except:
                warnings.warn("DAQ task did not successfully initialize")
                raise

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

        def release(self):
            try:
                self.StopTask()
                self.ClearTask()
            except:
                pass
    
    
    
    
    ######## DAQ for analog in #######
    class DAQIn(pydaq.Task):
        """
        From the perspective of the code instantiating the DAQIn class, expect the following:
        It will constantly read in data, adding to the data_q. that's it
        """
        def __init__(self, device='Dev1', ports=['ao0'], read_buffer_size=10, timeout=5., sample_rate=400., AI_mode=pydaq.DAQmx_Val_Diff, save_buffer_size=8000, analog_minmax=(-10,10)):
            
            # DAQ properties
            pydaq.Task.__init__(self)
            self.device = device
            self.port_names = ports
            self.ports = ['/'.join([self.device,port]) for port in self.port_names]
            self.timeout = timeout
            self.minn,self.maxx = analog_minmax
            self.sample_rate = sample_rate
            self.AI_mode = AI_mode

            # params & data
            self.read_success = pydaq.int32()
            self.read_buffer_size = read_buffer_size
            self.effective_buffer_size = self.read_buffer_size * len(self.ports)
            self.read_data = np.zeros(self.effective_buffer_size) # memory for DAQmx to write into on read callbacks
            self.last_ts = None
            self.data_q = mp.Queue()

            # Setup task
            try:
                self.CreateAIVoltageChan(','.join(self.ports), '', self.AI_mode, self.minn, self.maxx, pydaq.DAQmx_Val_Volts, None)
                self.CfgSampClkTiming('', self.sample_rate, pydaq.DAQmx_Val_Rising, pydaq.DAQmx_Val_ContSamps, self.read_buffer_size)
                self.AutoRegisterEveryNSamplesEvent(pydaq.DAQmx_Val_Acquired_Into_Buffer, self.read_buffer_size, 0)
                self.AutoRegisterDoneEvent(0)
        
                self.StartTask()
            except:
                warnings.warn("DAQ task did not successfully initialize")
                raise

        def EveryNCallback(self):
            # Auto-triggered by daqmx, adds new data to data queue

            self.last_ts = now()
            self.last_ts2 = now2()
            self.ReadAnalogF64(self.read_buffer_size, self.timeout, pydaq.DAQmx_Val_GroupByChannel, self.read_data, self.effective_buffer_size, pydaq.byref(self.read_success), None)
            if self.read_success:
                self.data_q.put([self.last_ts, self.last_ts2, self.read_data.copy()])
            else:
                warnings.warn('Failed to read despite callback having initiated read')
            
            return 0

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
            
