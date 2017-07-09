"""
This is a completely automated way of fixing corrupt data files, when analogreader is the culprit.

There are 2 steps, run 1 first then 2 second.

Step 1 will  copy the analogreader dataset to a temp file, automatically determining points of corruption and exlcuding them.
Step 2 will create a new data file, by merging analogreader from the temp file with all other datasets from the original data file. 

This script does not remove either the temp file (located in .) or the old data file.
"""

import pandas as pd, numpy as np
import tables

data_path = r'C:\\Users\\Wang_Lab\\Desktop\\puffs\\data\\data.h5'
temp = './temp.h5'
datanew = r'C:\\Users\\Wang_Lab\\Desktop\\puffs\\data\\data_new.h5'
out = pd.HDFStore(temp)
hdf = pd.HDFStore(data_path)
nexisting = hdf.get_storer('analogreader').nrows
chunk_size = 5e5

STEP = 2 # 1=copy out and fix corruption, 2=copy back in

if STEP == 1:

    for i in np.arange(np.ceil(float(nexisting)/chunk_size)):
        i0i = int(i*chunk_size)
        i1i = int(min(i*chunk_size+chunk_size, nexisting))
        print '{} : {}  /  {}   (*1000)'.format(i0i/1000,i1i/1000,nexisting/1000)
        
        okay = False
        corrupt = False
        decorrupt = None
        i0,i1 = i0i,i1i

        while okay is False:
            try:
                chunk = hdf.select('analogreader', start=int(i0), stop=int(i1))
            
                if corrupt is False:
                    out.append('artemp', chunk, index=False, data_columns=['session','subj','ts_global'], complevel=0)
                    okay = True
                elif corrupt:
                    if step == 1:
                        if decorrupt == 'bottom':
                            out.append('artemp', chunk, index=False, data_columns=['session','subj','ts_global'], complevel=0)
                            print 'Added subchunk {} - {}'.format(i0,i1)
                            i0 = i1
                            i1 = i1i
                            decorrupt = 'top'
                            step = chunk_size//2
                        elif decorrupt == 'top':
                            out.append('artemp', chunk, index=False, data_columns=['session','subj','ts_global'], complevel=0)
                            print 'Added subchunk {} - {}'.format(i0,i1)
                            okay = True
                    if decorrupt == 'bottom':
                        i1 += step
                        step = step//2
                    elif decorrupt == 'top':
                        i0 -= step
                        step = step//2

            except tables.HDF5ExtError:
                if corrupt is False:
                    print 'Corruption found in chunk {} - {}'.format(i0,i1)
                    corrupt = True
                    decorrupt = 'bottom'
                    step = chunk_size//2
                if decorrupt == 'bottom':
                    i1 -= step
                elif decorrupt == 'top':
                    i0 += step

    print 'Confirm that this worked, then run STEP2'

    
elif STEP == 2:
    ncopied = out.get_storer('artemp').nrows
    print 'table size original: {}\ntable size copied: {}\ndiff = {}'.format(nexisting,ncopied,nexisting-ncopied)
    go = raw_input( 'You are on step 2, which will copy all datasets to a new file. Confirm action (y/n): ')
    if go == 'y':
        dnew = pd.HDFStore(datanew)
        
        # copy all keys except AR
        for k in hdf.keys():
            if 'analogreader' in k:
                continue
            print k
            if 'sessions' in k:
                s = hdf[k]
                dnew.put(k, s)
            else:
                t = hdf[k]
                dnew.append(k, t, index=False, data_columns=['session','subj','ts_global'], complevel=0)
        # copy decorrupted AR
        for i in np.arange(np.ceil(float(ncopied)/chunk_size)):
            i0i = int(i*chunk_size)
            i1i = int(min(i*chunk_size+chunk_size, ncopied))
            print '{} : {}  /  {}   (*1000)'.format(i0i/1000,i1i/1000,ncopied/1000)
            chunk = out.select('artemp', start=int(i0i), stop=int(i1i))
            dnew.append('analogreader', chunk, index=False, data_columns=['session','subj','ts_global'], complevel=0)
        dnew.close()  
out.close()   
hdf.close()
print 'After step 2, recommended: confirm file handles "hdf", "out", "dnew" are closed.\n You may now want to now add any crashdump data to the new file, and set it as the main data file.'