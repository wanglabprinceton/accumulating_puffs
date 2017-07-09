"""
This is an example configuration file.
config.py is not copied to the repository because each rig has different parameters.
To make a usable version, copy this file into config.py and adjust as desired.
"""

import os

# global vars
TESTING_MODE = False
datafile = os.path.join('data','data.h5')

# rig params
email = 'john@doe.com'
rig_id = 0
reward_dur = [0.071,0.072]
spout_calibration           = dict( durations = [.063*i for i in [1., 1.2, 1.4, 1.6]], # secs
                                    volumes = [i/25. for i in [100, 125, 150, 175]] # uL
                                  )
stim_dur = 0.015
ar_params                   = dict(lick_thresh=3.5, moving_magnitude=5., ports=['ai2','ai3','ai4','ai5','ai6','ai0'], portnames=['lickl','lickr','puffl','puffr','galvo','hall'], runtime_ports=[0,1,5])
stimulator_params           = dict(ports=['port0/line0','port0/line1'], duration=stim_dur)
spout_params                = dict(ports=['port0/line2','port0/line3'], duration=reward_dur, calibration=spout_calibration)
light_params                = dict(port='port0/line4')
opto_params                 = dict(on=False) #dict(port='port0/line4')
scanimage_tcpip_address     = '128.112.217.150'
si_data_path                = r'D:\\deverett\\puffs'
ni845x_lines                = dict(start_acq=3, stop_acq=4)
go_cue                      = ''
motion_control              = False
mp285_params                = dict(leftright=(1,-1), vel=4000)
actuator_params             = dict(pos_retracted=0.05, pos_extended=0.15)
