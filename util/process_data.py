import pandas as pd
import os, sys, tables, warnings
from subprocess import call

warnings.simplefilter('ignore', tables.NaturalNameWarning)

puffs_dir = sys.argv[1]

data_dir_path = os.path.relpath(os.path.join(puffs_dir, 'data'))
data = os.path.relpath(os.path.join(data_dir_path, 'data.h5'))
trunc_file = os.path.relpath(os.path.join(data_dir_path, 'trunc.h5'))
comp_data = os.path.relpath(os.path.join(data_dir_path, 'data_compressed.h5'))

# Compress data, free disk space
print ('Compressing and freeing disk space...')
cmd = ' '.join(['ptrepack', '--overwrite', '--chunkshape=auto', '--complevel=9', '--complib=zlib', '\"{}\"'.format(data), '\"{}\"'.format(comp_data)])
ret = call(cmd)
if ret or not os.path.exists(comp_data):
    print('Data not properly ptrepack\'d.')

# Index data
print ('Indexing...')
d = pd.HDFStore(comp_data)
for tab in ['analogreader','light','phases','speaker','spout','stimulator','trials','trials_timing']:
    d.create_table_index(tab,columns=['session','subj','ts_global'], optlevel=9, kind='full')
d.close()

if os.path.exists(trunc_file):
    os.remove(trunc_file)
dt = pd.HDFStore(trunc_file)
with pd.HDFStore(comp_data) as d:
    dt.put('trials', d.trials, compression='zlib')
    dt.put('trials_timing', d.trials_timing, compression='zlib')
    for k in d.keys():
        if 'sessions' in k:
            dt.put(k, d[k], compression='zlib')
dt.close()

print ('Moving on to transfer...')
