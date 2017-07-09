from config import TESTING_MODE
from ctypes import c_int, c_void_p, c_char_p, c_float, c_uint16, c_uint32, c_uint8
from ctypes import Structure, byref
import os, time, json, sys, warnings, ctypes, logging, threading, h5py, Queue
import numpy as np
import multiprocessing as mp
from util import now,now2

if TESTING_MODE:
    from dummy import PSEye, default_cam_params

elif not TESTING_MODE:

    CLEYE_CODES = dict(
                        # camera sensor parameters
                        auto_gain                   =   0, #[false, true]
                        gain                        =   1, #[0, 79]
                        auto_exposure               =   2, #[false, true]
                        exposure                    =   3, #[0, 511]
                        auto_whitebalance           =   4, #[false, true]
                        whitebalance_red            =   5, #[0, 255]
                        whitebalance_green          =   6, #[0, 255]
                        whitebalance_blue           =   7, #[0, 255]
                        # camera linear transform parameters
                        hflip                       =   8, #[false, true]
                        vflip                       =   9, #[false, true]
                        hkeystone                   =   10, #[-500, 500]
                        vkeystone                   =   11, #[-500, 500]
                        xoffset                     =   12, #[-500, 500]
                        yoffset                     =   13, #[-500, 500]
                        rotation                    =   14, #[-500, 500]
                        zoom                        =   15, #[-500, 500]
                        # camera non-linear transform parameters
                        lens_correction1            =   16, #[-500, 500]
                        lens_correction2            =   17, #[-500, 500]
                        lens_correction3            =   18, #[-500, 500]
                        lens_brightness             =   19, #[-500, 500]
                        #CLEyeCameraColorMode
                        greyscale                   =   0,
                        colour                      =   1,
                        #CLEyeCameraResolution
                        qvga                        = 0,
                        vga                         = 1,
                    )

    ############# Special API Structures ################

    class GUID(Structure):
        _fields_ = [("Data1", c_uint32),
                 ("Data2", c_uint16),
                 ("Data3", c_uint16),
                 ("Data4", c_uint8 * 8)]
        def __str__(self):
            return "%X-%X-%X-%s" % (self.Data1, self.Data2, self.Data3, ''.join('%02X'%x for x in self.Data4))

    def CLEyeCameraGetFrameDimensions(dll, cam):
        width = c_int()
        height = c_int()
        dll.CLEyeCameraGetFrameDimensions(cam, byref(width), byref(height))
        return width.value, height.value

    def mp2np(a):
        return np.frombuffer(a.get_obj(), dtype=np.uint8)

    class MovieSaver(mp.Process):
        def __init__(self, name, kill_flag, frame_buffer, flushing, buffer_size=2000, hdf_resize=30000, min_flush=200, n_cams=1, resolution=None):
            super(MovieSaver, self).__init__()
            self.daemon = True

            # Saving params
            if not name.endswith('.h5'):
                name += '.h5'
            self.name = name
            self.buffer_size = buffer_size # should be overkill, since flushing will do the real job of saving it out
            self.hdf_resize = hdf_resize
            self.min_flush = min_flush
            
            # Cam params
            self.n_cams = n_cams
            self.resolution = resolution

            # Flags and containers
            self.saving_complete = mp.Value('b', False)
            self.kill_flag = kill_flag
            self.flushing = flushing
            self.frame_buffer = frame_buffer
            
            # Queries
            self.query_flag = mp.Value('b',False)
            self.query_queue = mp.Array(ctypes.c_uint8, np.sum([np.product(r) for r in self.resolution]))
            
            self.start()
        def run(self):
            
            # Setup hdf5 file and datasets
            self.vw_f = h5py.File(self.name,'w')
            self.vw,self.vwts = [],[]
            for i in range(self.n_cams):
                x,y = self.resolution[i]
                vw = self.vw_f.create_dataset('mov{}'.format(i), (self.hdf_resize, y, x), maxshape=(None, y, x), dtype='uint8', chunks=(14,y,x), compression='lzf') 
                vwts = self.vw_f.create_dataset('ts{}'.format(i), (self.hdf_resize,2), maxshape=(None,2), dtype=np.float64, compression='lzf')
                self.vw.append(vw)
                self.vwts.append(vwts)
               
            # Counters and buffers
            _sav_idx = [0]*self.n_cams # index within hdf5 dataset
            _buf_idx = [0]*self.n_cams # index of in-memory buffer that is periodicially dumped to hdf5 dataset
            _saving_buf,_saving_ts_buf = [],[]
            for i in range(self.n_cams):
                x,y = self.resolution[i]
                sb = np.empty((self.buffer_size,y,x), dtype=np.uint8)
                stb = np.empty((self.buffer_size,2), dtype=np.float64)
                _saving_buf.append(sb)
                _saving_ts_buf.append(stb)

            cams_running = [True for i in range(self.n_cams)]

            # Main loop
            while any(cams_running):
                # For all datasets: if there's not enough room to dump another buffer's worth into dataset, extend it
                # Then read new frames, and save/query as desired
                for di in range(self.n_cams):
                    if not cams_running[di]:
                        continue
                    
                    if self.vw[di].shape[0]-_sav_idx[di] <= self.buffer_size:
                        assert self.vw[di].shape[0] == self.vwts[di].shape[0], 'Frame and timestamp dataset lengths are mismatched.'
                        self.vw[di].resize((self.vw[di].shape[0]+self.hdf_resize, self.vw[di].shape[1], self.vw[di].shape[2]))
                        self.vwts[di].resize((self.vwts[di].shape[0]+self.hdf_resize,self.vwts[di].shape[1]))
               
                    # Get new frames from buffer, breaking out if empty and kill flag has been raised
                    ts=temp=bsave=None
                    try:
                        ts,temp,bsave = self.frame_buffer[di].get(block=False)
                    except Queue.Empty:
                        if self.kill_flag.value:
                            cams_running[di] = False
                        continue

                    if self.kill_flag.value==True:
                        logging.info('Final flush for camera {}: {} frames remain.'.format(di, self.frame_buffer[di].qsize()))
                                 
                    if self.query_flag.value:
                        res = self.resolution[di]
                        if di == 0:
                            start = 0
                        else:
                            start = np.product(self.resolution[:di])
                        self.query_queue[start:start+np.product(res)] = temp.copy()
                        if di == self.n_cams-1:
                            self.query_flag.value = False
                    
                    if bsave: # flag that this frame was added to queue during a saving period

                        # add new data to in-memory buffer
                        x,y = self.resolution[di]
                        _saving_buf[di][_buf_idx[di]] = temp.reshape([y,x])
                        _saving_ts_buf[di][_buf_idx[di]] = ts
                        _buf_idx[di] += 1
                        # if necessary, flush out buffer to hdf dataset
                        if (self.flushing.value and _buf_idx[di]>=self.min_flush) or _buf_idx[di] >= self.buffer_size:
                            if _buf_idx[di] >= self.buffer_size:
                                logging.warning('Dumping camera b/c reached max buffer (buffer={}, current idx={})'.format(self.buffer_size, _buf_idx[di]))
                            self.vw[di][_sav_idx[di]:_sav_idx[di]+_buf_idx[di],:,:] = _saving_buf[di][:_buf_idx[di]]
                            self.vwts[di][_sav_idx[di]:_sav_idx[di]+_buf_idx[di],:] = _saving_ts_buf[di][:_buf_idx[di]]
                            _sav_idx[di] += _buf_idx[di]
                            _buf_idx[di] = 0
  
                        
            # final flush:
            for di in range(self.n_cams):
                self.vw[di][_sav_idx[di]:_sav_idx[di]+_buf_idx[di],:,:] = _saving_buf[di][:_buf_idx[di]]
                self.vwts[di][_sav_idx[di]:_sav_idx[di]+_buf_idx[di]] = _saving_ts_buf[di][:_buf_idx[di]]
                _sav_idx[di] += _buf_idx[di]
                # cut off all unused allocated space 
                self.vw[di].resize([_sav_idx[di],self.vw[di].shape[1],self.vw[di].shape[2]])
                self.vwts[di].resize([_sav_idx[di],2])

            self.vw_f.close()
            
            self.saving_complete.value = True
    
    class PSEye():
        """
        Handles two distinct objects: the PSEye acqusition object, and the PSEye saving object, which run in separate processes
        """
        def __init__(self, idx, resolution_mode, frame_rate, color_mode, query_rate=1, save_name='noname', cleye_params=None, sync_flag=None):

            # CLEye Params; all should be tuples to allow for multiple cameras
            self.idx                = idx
            self.resolution_mode    = resolution_mode
            self.frame_rate         = frame_rate
            self.color_mode         = color_mode
            self.cleye_params       = cleye_params
            # Interfacing params
            self.query_rate         = query_rate
            self.save_name          = save_name

            # Special case for scenario where user uses shortcut for single camera, supplying straight params instead of n-length tuples
            if isinstance(self.idx, int):
                self.idx = (self.idx,)
                self.resolution_mode = (self.resolution_mode,)
                self.frame_rate = (self.frame_rate,)
                self.color_mode = (self.color_mode,)
                self.cleye_params = (self.cleye_params,)

            self.n_cams = len(self.idx)
            for o in [self.resolution_mode, self.frame_rate, self.color_mode, self.cleye_params]:
                assert len(o) == self.n_cams, 'All supplied camera parameters must be for the same number of cameras.'

            # Inferred params
            self.resolution = [_PSEye.DIMENSIONS[rm] for rm in self.resolution_mode]

            # Shared variables for acqusition and saving processes
            self.frame_buffer = [mp.Queue() for _ in range(self.n_cams)]
            self.kill_flag = mp.Value('b',False)
            self.saving = mp.Value('b', False)
            self.flushing = mp.Value('b', False)

            self.saver = MovieSaver(name=self.save_name, resolution=self.resolution, kill_flag=self.kill_flag, frame_buffer=self.frame_buffer, flushing=self.flushing, n_cams=self.n_cams)
            self.pseye = _PSEye(idx=self.idx, resolution_mode=self.resolution_mode, frame_rate=self.frame_rate, color_mode=self.color_mode, frame_buffer=self.frame_buffer, kill_flag=self.kill_flag, saving_flag=self.saving, sync_flag=sync_flag, cleye_params=self.cleye_params)

            self.last_query = now()            

        def get(self):
            if now()-self.last_query < 1./self.query_rate:
                return None
            self.last_query = now()
            self.saver.query_flag.value = True
            frs = []
            idx = 0
            full = mp2np(self.saver.query_queue)
            for r in self.resolution:
                nl = np.product(r)
                fr = full[idx:idx+nl].reshape(r[::-1])
                idx += nl
                frs.append(fr)
            return frs
        
        def reset_cams(self):
            self.pseye.reset_cams()

        def end(self):
            self.kill_flag.value = True
            while (not self.pseye.thread_complete.value) or (not self.saver.saving_complete.value):
                pass
        def begin_saving(self):
            self.saving.value = True
            
    class _PSEye(mp.Process):
        """
        An object that runs as its own process, serving the role of containing and calling the PSEye driver API
        Constantly checks for the presence of new frames and dumps them into multiprocessing queue
        """

        RES_SMALL = CLEYE_CODES['qvga']
        RES_LARGE = CLEYE_CODES['vga']  
        DIMENSIONS = {RES_SMALL:(320,240), RES_LARGE:(640,480)}
        available_framerates = {RES_LARGE:[15,30,40,50,60,75], RES_SMALL:[15,30,60,75,100,125]}
        COLOUR = CLEYE_CODES['colour']
        GREYSCALE = CLEYE_CODES['greyscale']
        BYTES_PER_PIXEL = {COLOUR:4, GREYSCALE:1}

        def __init__(self, idx, resolution_mode, frame_rate, color_mode, sync_flag=None, frame_buffer=None, kill_flag=None, saving_flag=None, cleye_params={}):

            # Process init
            super(_PSEye, self).__init__()
            self.daemon = True
            self.lib = "CLEyeMulticam.dll"

            # Camera Parameters : all are either legnth-1 or 2 tuples, corresponding to params for each camera
            self.idx = idx
            self.resolution_mode = resolution_mode
            self.frame_rate = frame_rate
            self.color_mode = color_mode
            self.cleye_params = cleye_params
            # Inferred parameters
            self.n_cams = len(self.idx)
            self.resolution = [self.DIMENSIONS[rm] for rm in self.resolution_mode]
            self.bytes_per_pixel = [self.BYTES_PER_PIXEL[cm] for cm in self.color_mode]
            self.read_dims = [r[::-1] for r in self.resolution]
            for i,cm in enumerate(self.color_mode):
                if cm == self.COLOUR:
                    self.read_dims[i].append(4)
            
            # Cross-process structures inherited from parent
            self.frame_buffer = frame_buffer
            self.kill_flag = kill_flag
            self.saving_flag = saving_flag

            # Runtime flags
            self.thread_complete = mp.Value('b',False)
            self.reset_cams_flag = mp.Value('b', False)

            # Sync
            self.sync_flag = sync_flag
            self.sync_val = mp.Value('d', 0)

            self.start()
        
        def cam_callback(self, idx, timeout=2000):
            while not self.kill_callbacks:
                if self.callbacks_paused[idx]:
                    continue
                got = self.dll.CLEyeCameraGetFrame(self._cams[idx], self._bufs[idx], timeout)
                if got: # this is actually useless, since API apparently returns strange values even in failed cases
                    ts,ts2 = now(),now2()
                    fr = np.frombuffer(self._bufs[idx], dtype=np.uint8).copy()
                    self.frame_buffer[idx].put([[ts,ts2],fr,self.saving_flag.value])
                    #print('Frame buffer {} size: {}'.format(idx,self.frame_buffer[idx].qsize()))
            self.callbacks_running[idx] = False
        
        def run(self):
            
            # Sync with parent process, if applicable
            # Waits for flag to be set, then reports current clock value
            while (not self.sync_flag is None) and (not self.sync_flag.value):
                self.sync_val.value = now()

            # Initialize camera
            self._init_cam()
            
            # setup buffers
            self._bufs = [ ctypes.create_string_buffer(np.product(res) * bpp) for res,bpp in zip(self.resolution,self.bytes_per_pixel) ]
           
            # setup callback-related variables
            self.kill_callbacks = False
            self.callbacks_running = [True for i in range(self.n_cams)]
            self.callbacks_paused = [False for i in range(self.n_cams)]
           
            # begin reading threads
            for i in range(self.n_cams):
                threading.Thread(target=self.cam_callback, args=(i,)).start()
           
            # Main loop
            while any(self.callbacks_running):
                if self.kill_flag.value:
                    self.kill_callbacks = True
                if self.reset_cams_flag.value:
                    self._reset_cams()
                        
            try:
                for c in self._cams:
                    self.dll.CLEyeCameraStop(c)
                    self.dll.CLEyeDestroyCamera(c)
            except:
                pass

            self.thread_complete.value = 1

        def reset_cams(self):
            # for calls made from other processes
            self.reset_cams_flag.value = True
            logging.info('Resetting cameras...')
        def _reset_cams(self):
            # for the process itself
            
            for i in range(len(self.callbacks_paused)):
                self.callbacks_paused[i] = True
                
            try:
                for c in self._cams:
                    self.dll.CLEyeCameraStop(c)
                    self.dll.CLEyeDestroyCamera(c)
            except:
                pass
            
            self._init_cam()

            for i in range(len(self.callbacks_paused)):
                self.callbacks_paused[i] = False
            
            self.reset_cams_flag.value = False
            logging.info('Cameras reset.')
        def _init_cam(self):
            
            # Load dynamic library
            self.dll = ctypes.cdll.LoadLibrary(self.lib)
            self.dll.CLEyeGetCameraUUID.restype = GUID
            self.dll.CLEyeCameraGetFrame.argtypes = [c_void_p, c_char_p, c_int]
            self.dll.CLEyeCreateCamera.argtypes = [GUID, c_int, c_int, c_float]
        
            n_cams_available = self.dll.CLEyeGetCameraCount()
            if n_cams_available < self.n_cams:
                warnings.warn('Fewer cameras available than requested.\n(Requested {}, {} available)'.format(self.n_cams, n_cams_available))
       
            self._cams = []
            for idx,cm,rm,fr in zip(self.idx,self.color_mode,self.resolution_mode,self.frame_rate):
                _cam = self.dll.CLEyeCreateCamera(self.dll.CLEyeGetCameraUUID(idx), cm, rm, fr)
                if not _cam:
                    raise Exception('Camera {} failed to initialize.'.format(idx))
                self._cams.append(_cam)
            
            # Confirmation of proper init
            for c,res in zip(self._cams, self.resolution):
                x,y = CLEyeCameraGetFrameDimensions(self.dll, c)
                assert (x,y)==res, 'Initialized camera\'s resolution does not match requested resolution.\nRequested: {}, Discovered: {}'.format(str(res), str((x,y)))

            for cleps,cam in zip(self.cleye_params, self._cams): # each camera
                for param in cleps: # each param
                    self.dll.CLEyeSetCameraParameter(cam, CLEYE_CODES[param], cleps[param])

            for c in self._cams:
                self.dll.CLEyeCameraStart(c)

            time.sleep(0.01)
        

##################################################################################################

    default_cam_params = dict(  idx=(0,1), 
                                resolution_mode=(_PSEye.RES_SMALL,_PSEye.RES_SMALL), 
                                query_rate = 0.5,
                                frame_rate=(30,30), 
                                color_mode=(_PSEye.GREYSCALE,_PSEye.GREYSCALE),
                                cleye_params = ( dict(
                                                       auto_gain = False,
                                                    auto_exposure = False,
                                                    auto_whitebalance = True,
                                                    gain = 5,
                                                    exposure = 14,
                                                    #whitebalance_red=100,
                                                    #whitebalance_blue=1,
                                                    #whitebalance_green=100,
                                                    vflip = False,
                                                    hflip = False,
                                                    rotation = False#-500,
                                                        ),
                                                dict(
                                                        auto_gain = False,
                                                    auto_exposure = False,
                                                    auto_whitebalance = True,
                                                    gain = 5,
                                                    exposure = 14,
                                                    #whitebalance_red=100,
                                                    #whitebalance_blue=1,
                                                    #whitebalance_green=100,
                                                    vflip = False,
                                                    hflip = False,
                                                    rotation = False#-500,
                                                        )
                                                )
            )
    cam1_params = dict(  idx=0, 
                                resolution_mode=_PSEye.RES_SMALL, 
                                query_rate = 0.5,
                                frame_rate=30, 
                                color_mode=_PSEye.GREYSCALE,
                                cleye_params = dict(
                                                        auto_gain = True,
                                                        auto_exposure = True,
                                                        auto_whitebalance = True,
                                                        vflip = False,
                                                        hflip = False,
                                                        rotation = False#-500,
                                                        ),

            )            
if __name__ == '__main__':

    cam_params = default_cam_params.copy()
    cam_params.update(idx=0,frame_rate=60,query_rate=1,save_name=r'C:\Users\deverett\Desktop\test1')
    cam = PSEye(**cam_params)
    time.sleep(4)
    #cam_params2 = default_cam_params.copy()
    #cam_params2.update(idx=0, frame_rate=60, save_name=r'C:\Users\deverett\Desktop\test2')
    #cam2 = PSEye(**cam_params2)
    #time.sleep(4)
    
    cam.begin_saving()
    #cam2.begin_saving()
    t0 = now()
    while now()-t0<10:
        fr = cam.get()
        #fr2 = cam2.get()
        if fr is not None:
            cv2.imshow('Camera View', fr)
        #if fr2 is not None:
        #    cv2.imshow('Camera View2', fr2)
        q = cv2.waitKey(1)
        if q == ord('q'):
            break
    cam.end()
    #cam2.end()
    cv2.destroyAllWindows()
    
