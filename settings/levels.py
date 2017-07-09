"""
Levels are the abstraction that holds advancing steps of training and the criteria required to advance through them.

A level consists of only params that must be considered on a trial-by-trial basis when generating trials. Specifically:
    -Criteria to advance to it
        -number of trials done in this level
        -window (number of CONTIGUOUS [i.e. no level-changes between them] trials) over which to assess following criteria
        -% correct in this level (of n=win valid trials)
        -% bias in this level (of n=win valid trials)
        -% valid in this level (of n=win trials of any kind)
    -Gamma
    -Rule
    -Manipulation
    -Durations
    -Intro: info about how many levels to move back to reintroduce this level in any given session

Levels are supplied to TrialHandler as a list, where each element is a subsequent level.
A given level is defined in a dict, with keys:
    "criteria" : a dict containing "n", "win", "perc", "valid", and "bias" keys, indicating the necessary values in this level to be considered "competent"
    "rule" : a rule value from the class constants
    "ratio" : either a value or a list of values (which will be randomly sampled).
    "manip" : either a value or a list of values (which will be randomly sampled). If None, will be filled in by ParamHandler using UI input
    "stim_phase_dur" : mean +- std
    "delay_phase_dur" : mean +- std
    "intro" : a list of 2-length tuples, where each tuple specifies (level ID, # to do at that level)
    
IMPORTANT NOTE:
    Do not edit the levels variable arbitrarily. The position of each level within the list is stored in every trial when saved, and this information is used to determine how an animal should be trained each session.
"""
from settings.rules import *
from settings.durations import stim_phase_durs, delay_phase_durs, long_delay
from manipulations import default_manipulation
from ratios import final_ratios, default_ratio, intro_ratios, hard_ratios

levels = [
            dict( #0 - free rewards
                    criteria = dict(    n=15,
                                        win=15,
                                        perc=0.0,
                                        bias=1.0,
                                        valid=0.9,
                                    ),

                    rule = RULE_PASSIVE,
                    ratio = default_ratio, 
                    manip = default_manipulation,
                    stim_phase_dur = stim_phase_durs[0],
                    delay_phase_dur = None,
                    stereo = (True, False),
                    alternate = True,
                    mp285_adjust_on = True,
                    intro = [],
                 ),
            
            dict( #1 - multiple tries
                    criteria = dict(    n=100,
                                        win=40,
                                        perc=0.55,
                                        bias=0.6,
                                        valid=0.5,
                                    ),

                    rule = RULE_FAULT,
                    ratio = default_ratio, 
                    manip = default_manipulation,
                    stim_phase_dur = stim_phase_durs[0],
                    delay_phase_dur = long_delay,
                    stereo = (True, False),
                    alternate = False,#True,
                    is_training = True, # training levels vs eventual performance levels
                    mp285_adjust_on = True,
                    intro = [(0, 6)],
                 ),
            dict( #2 - hints, short trials
                    criteria = dict(    n=200,
                                        win=50,
                                        perc=0.8,
                                        bias=0.6,
                                        valid=0.6,
                                    ),

                    rule = RULE_HINT,
                    ratio = default_ratio, 
                    manip = default_manipulation,
                    stim_phase_dur = stim_phase_durs[0],
                    delay_phase_dur = long_delay,
                    stereo = (True, True),
                    alternate = False, 
                    is_training = True,
                    mp285_adjust_on = True,
                    intro = [(1, 14)],
                 ),
            dict( #3 - full rule with short and long durations
                    criteria = dict(    n=100,
                                        win=40,
                                        perc=0.75,
                                        bias=0.6,
                                        valid=0.6,
                                    ),

                    rule = RULE_FULL,
                    ratio = default_ratio, 
                    manip = default_manipulation,
                    stim_phase_dur = stim_phase_durs[1],
                    delay_phase_dur = None,
                    stereo = (True, True),
                    alternate = False,
                    is_training = True,
                    mp285_adjust_on = True,
                    intro = [(2,30)],
                 ),
            dict( #4 - full rules & stim durs. training version
                    criteria = dict(    n=100,
                                        win=40,
                                        perc=0.80,
                                        bias=0.6,
                                        valid=0.6,
                                    ),

                    rule = RULE_FULL,
                    ratio = default_ratio, 
                    manip = default_manipulation,
                    stim_phase_dur = None,
                    delay_phase_dur = None,
                    stereo = (True, True),
                    alternate = False,
                    is_training = True,
                    mp285_adjust_on = True,
                    intro = [(2,15),(3, 15)],
                 ),
            dict( #5 - same as previous, but performance version
                    criteria = dict(    n=25,
                                        win=24,
                                        perc=0.80,
                                        bias=0.6,
                                        valid=0.6,
                                    ),

                    rule = RULE_FULL,
                    ratio = default_ratio, 
                    manip = None,
                    stim_phase_dur = None,
                    delay_phase_dur = None,
                    stereo = (True, True),
                    alternate = False,
                    is_training = False,
                    mp285_adjust_on = True,
                    intro = [(4,25)],
                 ),
            dict( #6 - full version, hardest ratio omitted
                    criteria = dict(    n=250,
                                        win=40,
                                        perc=0.78,
                                        bias=0.7,
                                        valid=0.8,
                                    ),

                    rule = RULE_FULL,
                    ratio = intro_ratios,
                    manip = None,
                    stim_phase_dur = None,
                    delay_phase_dur = None,
                    stereo = (True, True),
                    alternate = False,
                    is_training = False,
                    mp285_adjust_on = True,
                    intro = [(4,10), (5,10)], # 4 vs 5 only for training & manip reasons
                 ),
            dict( #7 - full task
                    criteria = dict(    n=950,
                                        win=50,
                                        perc=0.87,
                                        bias=0.7,
                                        valid=0.9,
                                    ),

                    rule = RULE_FULL,
                    ratio = final_ratios,
                    manip = None,
                    stim_phase_dur = None,
                    delay_phase_dur = None,
                    stereo = (True, True),
                    alternate = False,
                    is_training = False,
                    mp285_adjust_on = True,
                    intro = [(4,8), (5, 8), (6, 10),],
                 ),
            dict( #8 - full task extra hard
                    criteria = dict(    n=500000,
                                        win=500,
                                        perc=0.9,
                                        bias=0.5,
                                        valid=0.9,
                                    ),

                    rule = RULE_FULL,
                    ratio = hard_ratios,
                    manip = None,
                    stim_phase_dur = None,
                    delay_phase_dur = None,
                    stereo = (True, True),
                    alternate = False,
                    is_training = False,
                    mp285_adjust_on = True,
                    intro = [(4,12), (5, 12), (6, 30), (7,80)],
                 ),
            ]
