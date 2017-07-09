import numpy as np
import pandas as pd
import os, sys, h5py, time, logging
pjoin = os.path.join
import config
from hardware.valve import reward_scale_to_volume

def list_subjects():
    #subs = [d for d in os.listdir(data_path) if os.path.isdir(pjoin(data_path,d))]
    #return subs
    if not os.path.exists(config.datafile):
        return []
    with pd.HDFStore(config.datafile) as f:
        if 'trials' not in f:
            return []
        return f.trials.subj.unique().astype(int).astype(str)

def list_rewards():
    today = pd.datetime.now().date()
    if not os.path.exists(config.datafile):
        return {}
    with pd.HDFStore(config.datafile) as f:
        if 'trials' not in f:
            return {}
        tr = f.trials
        ses = tr.session
        tr = tr[ses.dt.date==today]
        res = {}
        for subn in tr.subj.unique():
            tsub = tr[tr.subj==subn]
            rewards = tsub.reward_scale[tsub.reward != False].values
            sides = tsub.side[tsub.reward != False].values
            rewards = [reward_scale_to_volume(int(si),rew) for si,rew in zip(sides,rewards)]
            res[str(int(subn))] = np.sum(rewards)
    return res
    print '%s: %i (%i uL)\t-->\tGive %i uL'%(s,r,r*4,1000-r*4)

class Subject(object):
    def __init__(self, name, data_path='./data'):
        # name check
        try:
            int(name)
        except:
            raise Exception('Subject name must be an integer')
        self.num = int(name)
        self.name = str(self.num)

        # directory
        self.subj_dir = os.path.abspath(pjoin(data_path, self.name))
        if not os.path.exists(self.subj_dir):
            os.mkdir(self.subj_dir)
            #print 'New subject \"%s\" created.'%self.name
        elif os.path.exists(self.subj_dir):
            pass
            #print 'Loaded subject \"%s\".'%self.name

    def get_position(self, kind):
        pos_path = self.get_pos_path(kind)
        with pd.HDFStore(config.datafile) as d:
            if not pos_path in d:
                logging.error('No position of kind \'{}\' found for {}'.format(kind,self.name))
                return [0,0,0]
            return np.asarray(d[pos_path]).tolist()
    def get_pos_path(self, kind):
        pos_path = '/'.join(['positions',self.name,kind])
        return pos_path
    def set_position(self, pos, kind):
        pos_path = self.get_pos_path(kind)
        assert isinstance(pos, np.ndarray) and len(pos)==3
        pos = pd.Series(dict(x=pos[0], y=pos[1], z=pos[2]))
        with pd.HDFStore(config.datafile) as d:
            if pos_path in d:
                d.remove(pos_path)
            d.put(pos_path, pos)
        logging.info('Subject {} {} position set to {}'.format(self.name, kind, str(pos.values)))
    def __json__(self):
        return dict(name=self.name, path=self.subj_dir)
