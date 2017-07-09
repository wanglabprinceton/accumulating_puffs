import numpy as np
import copy
from expts.session import Session as S
from hardware.cameras import default_cam_params, cam1_params
from conditions import default_condition, conditions
from settings.manipulations import default_manipulation
from settings.durations import default_stim_phase_duration, default_delay_phase_duration
from levels import levels
from ratios import default_ratio
import config, logging
from settings.constants import *

class ParamHandler(object):
    """
    The ParamHandler class aggregates input from defaults, UI selections, and other sources, to provide a complete set of parameters to supply to a session when initiating.
    When the software is run from the UI, it instantiates a ParamHandler object and passes its params to the session it creates.
    """

    basics = dict(

        name                            = None,

        # Trial parameters
        trial_params =  dict(
            rate_sum                    = 2.5,
            stim_duration               = config.stim_dur,
            stim_phase_duration         = default_stim_phase_duration,
            stim_phase_pad              = [0.0, 0.050],
            min_isi                     = 0.200,
            delay_phase_duration        = default_delay_phase_duration,
            start_level                 = -1,
            alternate_training_levels   = True,
            # Anti-biasing parameters
            bias_correction             = 6,
            max_bias_correction         = 0.2, # the lower num, any biases stronger than this are bumped to this
            min_bias_for_correction     = 0.6, # the higher number, won't correct biases weaker than this           
            reward_scaling_threshold    = 0.3, # bias value at which reward scaling kicks in
            antibias_reward_scales      = [1.0, 1.2, 1.4],
            mp285_adjust_threshold      = .3,
            mp285_adjust_nthreshold     = 5,
            mp285_adjust_max_adjusts    = 8,       ),

        # Hardware parameters
        ar_params                   = config.ar_params,
        stimulator_params           = config.stimulator_params,
        spout_params                = config.spout_params,
        light_params                = config.light_params,
        opto_params                 = config.opto_params,
        actuator_params             = config.actuator_params,

        # Timing parameters
        phase_durations             = {      PHASE_INTRO:1.0,\
                                             PHASE_STIM:None,\
                                             PHASE_DELAY:None,\
                                             PHASE_LICK:5.0,\
                                             PHASE_REWARD:3.0,\
                                             PHASE_ITI:3.5,\
                                             PHASE_END:0.0 },
        penalty_iti_frac            = 1.7,
        enforce_stim_phase_duration = True,

        # Rule parameters
        hold_rule                   = True,
        lick_rule_phase             = True,
        lick_rule_side              = True,
        lick_rule_any               = True, 
        use_trials                  = True,
        puffs_on                    = True,
        rewards_on                  = True,
        hint_interval               = (0.400,0.001),
        go_cue                      = config.go_cue,
        motion_control              = config.motion_control, # like wheel

        # Movie parameters
        cam_params                  = default_cam_params, #cam1_params,

        # Experiment parameters
        subj                        = None,
        condition                   = None,
        imaging                     = False,
        position_stim               = None,
        position_lick               = None,
        retract_ports               = True,
      )


    def __init__(self, subj, condition=default_condition, manipulation=default_manipulation, start_level=-1, imaging=False, position=None):
        self.subj = subj
        self.params = self.basics
        self.manip = manipulation
        self.position_stim = self.subj.get_position('stim')
        self.position_lick = self.subj.get_position('lick')
        self.params.update(subj=self.subj, condition=condition, imaging=imaging, position_stim=self.position_stim, position_lick=self.position_lick)
        
        if config.TESTING_MODE:
            #self.params['trial_params'].update(stim_phase_duration=[0.5,0.05], delay_phase_duration=[0.5,0.05])
            self.params['phase_durations'] = {       PHASE_INTRO:0.1,\
                                                     PHASE_STIM:None,\
                                                     PHASE_DELAY:None,\
                                                     PHASE_LICK:0.1,\
                                                     PHASE_REWARD:0.1,\
                                                     PHASE_ITI:1.0,\
                                                     PHASE_END:0.0 }
        levels_ = copy.deepcopy(levels)
        for l in levels_:
            if l['manip'] is None:
                l['manip'] = self.manip
        self.params['trial_params'].update(levels=levels_, start_level=start_level)
        #if condition in [conditions['cno02'], conditions['sal02']]:
        #    self.params['trial_params'].update(bias_correction=None)
        #    logging.info('Bias correction turned off due to condition selection.')
            
        if config.antibiasing is False:
            self.params['trial_params'].update(bias_correction=None)
