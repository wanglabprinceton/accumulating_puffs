## RUN IN PYTHON 2x !!!!!!!!

from soup.classic import *
=======
import pandas as pd
import numpy as np

spkr_dict = {'media/error.wav':0, 'media/pop.wav':1, 'media/laser.wav':2, 'media/intro.wav':3, 'media/buzz.wav':4}

d = pd.HDFStore('data.h5')
dnew = pd.HDFStore('data_new.h5')
for tab in d.keys():
    print(tab)
    tab = tab.strip('/')
    if 'sessions' in tab:
        dnew.put(tab, d[tab])
        continue
    
    datanew = d[tab]
    datanew.subj[datanew.subj=='testsub'] = '00'
    datanew.subj = datanew.subj.str[1:].astype(np.float64)
    datanew.session = datanew.session.str[1:].str.replace('_','').astype(np.float64)
    if tab == 'speaker':
        datanew.filename = [spkr_dict[i] for i in datanew.filename]
        datanew.filename = datanew.filename.astype(np.int)
    dnew.append(tab, datanew, chunksize=2e6, index=False, data_columns=['session','subj','ts_global'])

d.close()
dnew.close()
