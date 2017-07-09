"""
To start using a new datafile
Rename current one, then run a dummy session to create a new file
Then run this
It will include 2 trials from each unique subject, plus their mp285 positions
"""

import pandas as pd

old_file_path = r'C:\\Users\\Wang_Lab\\Desktop\\puffs\\data\\data_part0.h5'
new_file_path = r'C:\\Users\\Wang_Lab\\Desktop\\puffs\\data\\data.h5'

d0 = pd.HDFStore(old_file_path)
dnew = pd.HDFStore(new_file_path)

pkeys = [k for k in d0.keys() if 'position' in k]
for pk in pkeys:
    dnew.put(pk, d0[pk])
usub = d0.trials.subj.unique()
for us in usub:
    trials = d0.trials[d0.trials.subj==us]
    trials = trials.iloc[-2:]
    dnew.append('trials', trials, index=False, data_columns=['session','subj','ts_global'], complevel=0)
 
d0.close()
dnew.close()