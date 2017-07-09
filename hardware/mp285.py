import numpy as np, pandas as pd
import config
import serial, struct, warnings, threading, logging
try:
    import win32api
except:
    pass

MINPOS = -9500
MAXPOS = 9500	
	
"""
    To reset weird bugs (will miscalibrate): 
    -remove everything from the device. 
    -center axes using buttons on controller
    -open an MP285 instance and run .zero()
    -confirm that get_pos is 0,0,0 and that if you goto 0,0,0 it doesn't move
    -close that object
    -open another instance and confirm that again (if it moves to some random place when you goto 0,0,0, start from step 1 but try skipping the step where you "zero")
    -close that instance

    The maximal speeds that can be commanded at both resolutions are 1330mm/s at
    0.04mm/mstep and 6550mm/s at 0.20mm/mstep. 

    change vel:
    056h + one unsigned short (16-bit) integer + 0Dh
    Note: The lower 15 bits (Bit 14 through 0) contain
    the velocity value. The high-order bit (Bit 15) is
    used to indicate the microstep-to-step resolution: 
    0 = 10, 1 = 50 uSteps/step
"""

def set_mp285_home(pos):
    homepath = 'positions/home'
    assert isinstance(pos, np.ndarray) and len(pos)==3
    pos = pd.Series(dict(x=pos[0], y=pos[1], z=pos[2]))
    with pd.HDFStore(config.datafile) as d:
        if homepath in d:
            d.remove(homepath)
        d.put(homepath, pos)
    logging.info('Home position set to {}'.format(str(pos.values)))
    
def get_mp285_home():
    homepath = 'positions/home'
    with pd.HDFStore(config.datafile) as d:
        if homepath not in d:
            warnings.warn('No home set.')
            return
        return d[homepath]

class MP285():
    ABS,REL = 0,1
    def __init__(self, port='COM1', baudrate=9600, timeout=40, vel=6000, leftright=(1,-1), nudge_increment=50):
        # leftright speficies which directions (-1,1) or opposite, correspond in x axis to left and right
        # specifically: the first item in leftright is the sign to make a leftward movement
        self.vel = vel
        self.leftright = leftright
        self.nudge_increment = nudge_increment
        try:
            self.ser = serial.Serial(port=port, baudrate=baudrate, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, timeout=timeout)
            self.setup()
            self.purge()
        except:
            warnings.warn('MP285 failed to initialize.')
        self.lock = threading.Lock()
        self.is_moving = False
        self.saver = None
    
    def word_to_val(self, w):
        return w[1]*256 + float(w[0])
    
    def purge(self):
        self.ser.flushInput()
        self.ser.flushOutput()
        self.ser.flush()
        
    def setup(self):
        self.set_mode(self.REL)
        stat = self.get_status()
        self.step_mult = self.word_to_val(stat['step_mult'])
        self.step_div = self.word_to_val(stat['step_div'])
        self.uoffset = self.word_to_val(stat['uoffset'])
        
        self.set_velocity(self.vel)
    def get_status(self):
        self.purge()
        self.ser.write('s\r')
        stat = self.ser.read(32)
        self._wait()
        stat = struct.unpack(32*'B', stat)
        
        FLAGS,UDIRX,UDIRY,UDIRZ = stat[0:4]
        ROE_VARI = stat[4:6]
        UOFFSET = stat[6:8]
        URANGE = stat[8:10]
        PULSE = stat[10:12]
        USPEED = stat[12:14]
        INDEVICE = stat[14]
        FLAGS_2 = stat[15]
        JUMPS_PD = stat[16:18]
        HIGHSPD = stat[18:20]
        DEAD = stat[20:22]
        WATCH_DOG = stat[22:24]
        STEP_DIV = stat[24:26]
        STEP_MULT = stat[26:28]
        XSPEED = stat[28:30] # in mm/s according to manual
        VERSION = stat[30:32]
                
        self.purge()
        return dict(step_div=STEP_DIV, step_mult=STEP_MULT, uoffset=UOFFSET, xspeed=XSPEED)
    
    def get_velocity(self):
        self.purge()
        res = self.get_status()
        v = res['xspeed']
        byte0 = '{:8b}'.format(v[0]).replace(' ','0')
        byte1 = '{:8b}'.format(v[1]).replace(' ','0')
        
        # extract resolution bit:
        resolution = int(byte0[0])
        byte0 = '0'+byte0[1:]
        
        word = byte0+byte1
        word = eval('0b{}'.format(word))
        return word, resolution # speed is in mm/s according to manual
    
    def get_pos(self):
        self.purge()
        self.ser.write('c\r')
        pos = self.ser.read(13)
        pos = np.array(struct.unpack('lll', pos[:12]))
        self.purge()
        return pos/self.step_div

    def goto(self, pos):
        # units are microns

        pos_input = np.asarray(pos)
        pos = pos_input.copy()
        # confirm will not go out of bounds
        if np.any(pos<MINPOS) or np.any(pos>MAXPOS):
            logging.warning('MP285 move cancelled, would go out of boundaries.')
            return
        
        with self.lock:
            self.purge()
            self.is_moving = True
            assert len(pos)==3
            pos = np.asarray(pos) * self.step_div
            pos = struct.pack('lll', *pos)
            self.ser.write('m'+pos+'\r')
            self._wait()
            self.purge()
        self.is_moving = False
        #self.refresh()

        if self.saver is not None:
            pc = pos_input
            self.saver.write('mp285', dict(x=float(pc[0]), y=float(pc[1]), z=float(pc[2])))

    def nudge(self, direction):
        # an x-axis nudge movement
        _dir = self.leftright[direction]
        pos = self.get_pos()
        inc = np.array([_dir*self.nudge_increment, 0, 0])
        pos += inc
        self.goto(pos)
        
    def set_velocity(self, vel, ustep_resolution=50):
        self.purge()
        assert vel<2**15
        vel = '{:15b}'.format(vel).replace(' ','0')
        
        ustep_dic = {50:'1', 10:'0'}
        vel = ustep_dic[ustep_resolution] + vel
        assert len(vel)==16
        
        vel = chr(eval('0b{}'.format(vel[:8]))) + chr(eval('0b{}'.format(vel[8:])))
            
        self.ser.write('V'+vel+'\r')
        self._wait()
        #self.refresh()
        self.purge()
        
    def set_mode(self, mode):
        # MP285.ABS or MP285.REL
        self.purge()
        ch = {self.ABS:'a', self.REL:'b'} 
        self.ser.write(ch[mode]+'\r')
        self._wait()
        self.purge()
        #self.refresh()

    def zero(self, warn=True, force=False):
        warnings.warn('Zero function disabled for protection; mp285 has been calibrated and zeroing it will cause undesired behaviour.')
        if not force:
            return
        if force:
            ok = raw_input('Are you sure you want to zero?')
        if ok != 'y':
            return
        self.ser.write('o\r')
        self._wait()
        self.refresh(force=True)
        if warn:
            win32api.MessageBox(0, 'Zero MP285 manually now for smoother experience.', 'MP285', 0x00001000) 

    def refresh(self, force=False):
        warnings.warn('Refresh disabled.')
        if not force:
            return
        elif force:
            self.ser.write('n\r')
            self._wait()

    def _wait(self):
        ret = self.ser.read(1)
        if ret != '\r':
            warnings.warn('Failure to receive reply from MP285 device.')
        #assert self.ser.inWaiting()==0

    def reset(self):
        self.ser.write('r\r')

    def end(self):
        try:
            self.purge()
            self.ser.close()
        except:
            pass
