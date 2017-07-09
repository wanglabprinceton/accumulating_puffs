import sys, os, threading, h5py, json, warnings, tables, logging, config, Queue, time
import multiprocessing as mp
import numpy as np
import pandas as pd
from util import now,now2
from routines import add_to_saver_buffer

class Saver(mp.Process):
    # To save, call saver.write() with either a dict or a numpy array
    # To end, just use the saver.end method. It will raise a kill flag, then perform a final flush.

    def __init__(self, subj, sesh_name, session_obj, data_file=config.datafile, sync_flag=None, field_buffer_size=30, forced_flush_fieldnames=dict(analogreader=5)):
        super(Saver, self).__init__()

        # Sync
        self.sync_flag = sync_flag
        self.sync_val = mp.Value('d', 0)

        # Static instance properties
        self.subj = subj
        self.sesh_name = sesh_name
        self.session_obj = session_obj
        self.data_file = data_file
        self.sesh_path = ['sessions', self.sesh_name.strftime('%Y%m%d%H%M%S')]
        self.past_trials = self.get_past_trials()
        self.field_buffer_size = field_buffer_size
        self.forced_flush_fieldnames = forced_flush_fieldnames # used to indicate special fields that should be flushed when n items have been supplied. format: {fieldname:n}

        # Externally accessible flags and variables
        self.buf = mp.Queue()
        self.notes_q = mp.Queue()
        self.kill_flag = mp.Value('b', False)

        self.start()

    def write(self, *args, **kwargs):
        if self.kill_flag.value:
            return

        add_to_saver_buffer(self.buf, *args, **kwargs)
        
    def run(self):
        while not self.sync_flag.value:
            self.sync_val.value = now()

        # Externally inaccessible instance-specific structures
        self.f = pd.HDFStore(self.data_file, mode='a')
    
        # Save session details
        warnings.simplefilter('ignore', tables.NaturalNameWarning)
        param_path = '/'.join(self.sesh_path + ['params'])
        code_path = '/'.join(self.sesh_path + ['code'])
        sync_path = '/'.join(self.sesh_path + ['sync'])
        self.f.put(param_path, pd.Series(json.dumps(self.session_obj.params, cls=JSONEncoder)))
        self.f.put(code_path, pd.Series(self.session_obj.get_code()))
        while self.session_obj.sync_to_save.empty():
            pass
        sy = self.session_obj.sync_to_save
        self.f.put(sync_path, pd.Series(sy.get()))

        # main loop runtime vars
        field_buffers = {}

        # Main loop
        # Continuously reads from buffer queue, saving data if present
        while True:
            if self.buf.empty() and self.kill_flag.value:
                break
               
            try:
                record = self.buf.get(block=False)
            except Queue.Empty:
                continue

            if self.kill_flag.value:
                logging.info('Saver final flush: {} items remain.'.format(self.buf.qsize()))
            
            source,data,ts,ts2,columns = record
            if not isinstance(data, pd.DataFrame):
                data = pd.DataFrame(data, columns=columns, index=[ts])
            elif isinstance(data, pd.DataFrame):
                data.set_index([[ts]*len(data)], inplace=True)
            data.ix[:,'session'] = self.sesh_name
            data.ix[:,'subj'] = np.float64(self.subj.num)
            data.ix[:,'ts_global'] = ts2

            # add to source-specific buffer
            if source not in field_buffers:
                field_buffers[source] = [data]
            elif source in field_buffers:
                field_buffers[source].append(data)

            # write to file if pertinent
            if len(field_buffers[source]) >= self.field_buffer_size or (source in self.forced_flush_fieldnames and len(field_buffers[source])>=self.forced_flush_fieldnames[source]):
                to_write = pd.concat(field_buffers[source])
                try:
                    self.f.append(source, to_write, index=False, data_columns=['session','subj','ts_global'], complevel=0)
                except:
                    logging.error('Failure to save record of type \'{}\''.format(source))
                    logging.error(sys.exc_info())
                    with pd.HDFStore('crashdump_{:0.11f}'.format(time.time())) as cra:
                        cra.append(source, to_write, index=False, data_columns=['session','subj','ts_global'], complevel=0)
                    #raise
                field_buffers[source] = []
        # end main loop

        # final write:
        for key in field_buffers:
            if len(field_buffers[key]):
                to_write = pd.concat(field_buffers[key])
            else:
                continue
            try:
                self.f.append(key, to_write, index=False, data_columns=['session','subj','ts_global'], complevel=0)
            except:
                logging.error('Failure to save record of type \'{}\' (in final saving section)'.format(key))
                logging.error(sys.exc_info())
                logging.error(to_write)
                logging.error('orig list:')
                logging.error(field_buffers[key])
                with pd.HDFStore('crashdump_{:0.11f}'.format(time.time())) as cra:
                    cra.append(key, to_write, index=False, data_columns=['session','subj','ts_global'], complevel=0)
                #raise
            field_buffers[key] = []

        notes_path = '/'.join(self.sesh_path + ['notes'])
        try:
            self.f.put(notes_path, pd.Series(json.dumps(self.notes_q.get(), cls=JSONEncoder)))
        except:
            with open('crash.backup','a') as cra:
                cra.write(str(notes))
            logging.error('Notes failed to save. Backed up into crash.backup')

        self.f.close()
                    
    def get_past_trials(self, lastlevel=True):
        if not os.path.exists(self.data_file):
            return None

        with pd.HDFStore(self.data_file, mode='r') as f:
            if 'trials' not in f:
                return None

            tris = f.trials
        
        if len(tris) == 0:
            return None

        tris = tris[tris.subj==self.subj.num]
        if len(tris) == 0:
            return None

        if lastlevel:
            pastlevs = np.asarray(tris.level)
            lev = pastlevs[-1]
            if all(pastlevs==lev):
                pass
            else:
                fromi = np.argwhere(pastlevs!=lev).squeeze()
                if fromi.ndim>0:
                    fromi = fromi[-1]
                fromi = int(fromi + 1)
                tris = tris.iloc[fromi:]

        return tris

    def end(self, notes={}):
        self.notes_q.put(notes)
        self.kill_flag.value = True

class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, '__json__'):
            return obj.__json__()
        return json.JSONEncoder.default(self, obj)
