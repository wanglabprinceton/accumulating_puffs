import numpy as np
import pandas as pd
import time, threading, os, logging, csv, json, multiprocessing
from hardware import AnalogReader, Valve, Light, PSEye, Speaker, default_cam_params, Opto, SICommunicator
from settings.manipulations import *
from settings.constants import *
from trials import TrialHandler
from saver import Saver
from util import now, email_alert
import config
pjoin = os.path.join

class Session(object):

    DEFAULT_PARAMS = {}

    def __init__(self, session_params, mp285=None, actuator=None):
        self.params = self.DEFAULT_PARAMS

        # incorporate kwargs
        self.params.update(session_params)
        self.__dict__.update(self.params)
        self.verify_params()

        # sync
        self.sync_flag = multiprocessing.Value('b', False)
        self.sync_to_save = multiprocessing.Queue()

        # saver
        self.saver = Saver(self.subj, self.name, self, sync_flag=self.sync_flag)

        # hardware
        self.cam = PSEye(sync_flag=self.sync_flag, **self.cam_params)
        self.ar = AnalogReader(saver_obj_buffer=self.saver.buf, sync_flag=self.sync_flag, **self.ar_params)
        self.stimulator = Valve(saver=self.saver, name='stimulator', **self.stimulator_params)
        self.spout = Valve(saver=self.saver, name='spout', **self.spout_params)
        self.light = Light(saver=self.saver, **self.light_params); self.light.set(0)
        self.opto = Opto(saver=self.saver, **self.opto_params)
        self.speaker = Speaker(saver=self.saver)
        
        # mp285, actuator
        self.mp285 = mp285
        self.actuator = actuator
        self.actuator.saver = self.saver
        self.mp285_go(self.position_stim)
        if self.retract_ports:
            self.actuator.retract()
            #self.mp285_go(self.position_stim)
        else:
            self.actuator.extend()
            #self.mp285_go(self.position_lick)

        # communication
        self.sic = SICommunicator(self.imaging)

        # trials
        self.th = TrialHandler(saver=self.saver, condition=self.condition, **self.trial_params)

        # runtime variables
        self.stdinerr = None
        self.notes = {}
        self.session_on = 0
        self.session_complete = False
        self.session_kill = False
        self.session_runtime = -1
        self.trial_runtime = -1
        self.rewards_given = 0
        self.paused = 0
        self.holding = False
        self.current_phase = PHASE_INTRO
        self.live_figure = None
        
        # sync
        self.sync_flag.value = True #trigger all processes to get time
        self.sync_val = now() #get this process's time
        procs = dict(saver=self.saver, cam=self.cam.pseye, ar=self.ar)
        sync_vals = {o:procs[o].sync_val.value for o in procs} #collect all process times
        sync_vals['session'] = self.sync_val
        self.sync_to_save.put(sync_vals)

    def name_as_str(self):
        return self.name.strftime('%Y%m%d%H%M%S')

    def verify_params(self):
        if self.name is None:
            self.name = pd.datetime.now()
        logging.info('Session: {}'.format(self.name))
        self.cam_params.update(dict(save_name=pjoin(self.subj.subj_dir, self.name_as_str())))

    def pause(self, val):
        if val is True:
            self.paused += 1
            self.light.set(0)
            #self.sic.stop_acq()
        elif val is False:
            self.paused = max(self.paused-1,0)
            if self.paused == 0:
                self.sic.start_acq()
        
    def stimulate(self):
        n = len(self.th.trt)
        t0 = now()
        while self.current_phase == PHASE_STIM and self.stim_idx < n:
            dt = now() - t0
            if dt >= self.th.trt['time'][self.stim_idx]:
                #logging.debug(dt-self.th.trt['time'][self.stim_idx])
                self.stimulator.go(self.th.trt['side'][self.stim_idx])
                self.stim_idx += 1
        
    def to_phase(self, ph):
        # Write last phase
        if not (self.th.idx==0 and ph==0):
            phase_info = dict(  trial = self.th.idx, 
                                phase = self.current_phase,
                                start_time = self.phase_start, 
                                end_time = now(),
                             )
            self.saver.write('phases',phase_info)

        self.current_phase = ph

        # tell imaging
        self.sic.i2c('{}.{}'.format(self.th.idx, self.current_phase))

        # determine duration
        if self.current_phase==PHASE_STIM:
            self.current_phase_duration = self.th.phase_dur
        elif self.current_phase==PHASE_DELAY:
            self.current_phase_duration = self.th.delay_dur
        else:
            self.current_phase_duration = self.phase_durations[ph] #intended phase duration

        self.phase_start = now()
        self.last_hint = now()

        # Flush flag for camera:
        if ph in [PHASE_ITI, PHASE_END]:
            self.cam.flushing.value = True
        else:
            self.cam.flushing.value = False

        # Opto LED : based on constants defined in manipulations.py
        if self.th.manip == MANIP_NONE:
            self.opto.set(0)
        elif self.th.manip == MANIP_OPTO_STIMDELAY and self.current_phase in [PHASE_STIM,PHASE_DELAY]:
            self.opto.set(1)
        elif self.th.manip == MANIP_OPTO_LICK and self.current_phase == PHASE_LICK:
            self.opto.set(1)
        elif self.th.manip == MANIP_OPTO_REWARDITI and self.current_phase in [PHASE_REWARD,PHASE_ITI]:
            self.opto.set(1)
        else:
            self.opto.set(0)

        # Trial ending logic
        if ph == PHASE_END:
            lpl = self.licks[self.licks['phase']==PHASE_LICK] #lick phase licks

            # sanity check. should have been rewarded only if solely licked on correct side
            if self.th.rule_side and self.th.rule_phase and (not self.licked_early) and (not self.th.rule_fault) and self.use_trials:
                assert bool(self.rewarded) == (any(lpl['side']==self.th.trial.side) and not any(lpl['side']==-self.th.trial.side+1))
            
            # determine trial outcome
            if not self.use_trials:
                if any(lpl):
                    outcome = COR
                else:
                    outcome = INCOR
            elif not self.th.rule_any:
                lprl = self.licks[(self.licks['phase']==PHASE_LICK) | (self.licks['phase']==PHASE_REWARD)]
                if not any(lprl):
                    outcome = NULL
                elif lprl[0]['side'] == self.th.trial.side:
                    outcome = COR
                else:
                    outcome = INCOR
            elif self.use_trials:
                if self.rewarded and self.th.rule_side and not self.th.rule_fault:
                    outcome = COR
                elif self.rewarded and ((not self.th.rule_side) or self.th.rule_fault):
                    if not any(lpl):
                        outcome = NULL
                    else:
                        if lpl[0]['side'] == self.th.trial.side:
                            outcome = COR
                        else:
                            outcome = INCOR
                elif self.trial_kill:
                    outcome = KILLED
                elif self.licked_early:
                    outcome = EARLY[self.licked_early['side']]
                elif any(lpl['side']==-self.th.trial.side+1):
                    outcome = INCOR
                elif not any(lpl):
                    outcome = NULL
            # Save trial info
            nLnR = self.stimulator.get_nlnr()
            if config.TESTING_MODE:
                fake_outcome = np.random.choice([COR, INCOR, EARLY_L, EARLY_R, NULL, KILLED], p=[0.5,0.3,0.15/2,0.15/2,0.04,0.01])
                self.th.end_trial(fake_outcome, -0.1*(fake_outcome==COR), nLnR)
                if fake_outcome == COR:
                    self.rewards_given += 1
            else:
                self.th.end_trial(outcome, self.rewarded, nLnR)

    def update_licked(self):
        l = self.ar.licked
        tst = now()
        for idx,li in enumerate(l):
            if li:
                try:
                    self.licks[self.lick_idx] = (self.current_phase, tst, idx)
                    self.lick_idx += 1
                except:
                    logging.error(self.licks)
                if self.lick_idx >= len(self.licks):
                    self.licks = self.licks.resize(len(self.licks)+2000)
                
        
        if self.hold_rule:
            if (not self.holding) and np.any(self.ar.holding):
                self.holding = True
                self.pause(True)
            elif self.holding and not np.any(self.ar.holding):
                self.pause(False)
                self.holding = False
            if self.holding:
                self.speaker.pop(wait=False)

            
    def run_phase(self):
        ph = self.current_phase
        ph_dur = self.current_phase_duration
        dt_phase = now() - self.phase_start
        self.session_runtime = now() - self.session_on
        self.trial_runtime = now() - self.th.trial.start
        self.update_licked()

        # special cases
        if ph == PHASE_ITI and not self.rewarded:
            ph_dur *= 1+self.penalty_iti_frac

        if self.paused and self.current_phase in [PHASE_INTRO,PHASE_STIM,PHASE_DELAY,PHASE_LICK]:
            self.trial_kill = True
            return

        if self.trial_kill and not self.current_phase==PHASE_ITI:
            self.to_phase(PHASE_ITI)
            return

        # Intro
        if ph == PHASE_INTRO:
            self.light.set(0)
            if not self.intro_signaled:
                self.speaker.intro()
                self.intro_signaled = True
            if dt_phase >= ph_dur:
                self.to_phase(PHASE_STIM)
                return
            
        # Stim
        elif ph == PHASE_STIM:
            if self.th.rule_phase and any(self.licks['phase']==PHASE_STIM):
                self.licked_early = self.licks[0]
                self.to_phase(PHASE_ITI)
                return
            
            if dt_phase >= ph_dur:
                self.to_phase(PHASE_DELAY)
                return
            
            if self.puffs_on and not self.stimulated:
                threading.Thread(target=self.stimulate).start()
                self.stimulated = True

        # Delay
        elif ph == PHASE_DELAY:
            if any(self.licks['phase']==PHASE_DELAY) and self.th.rule_phase:
                self.licked_early = self.licks[0]
                self.to_phase(PHASE_ITI)
                return
                    
            if dt_phase >= ph_dur:
                self.to_phase(PHASE_LICK)
                return
            
            if self.th.rule_hint_delay and now()-self.last_hint > self.next_hint_interval:
                self.stimulator.go(self.th.trial.side)
                self.last_hint = now()
                
                self.next_hint_interval = np.random.normal(*self.hint_interval)
                if self.next_hint_interval<0:
                    self.next_hint_interval = self.hint_interval[0]
            
        # Lick
        elif ph == PHASE_LICK:

            #if self.retract_ports and (self.mp285 is not None) and (not self.moved_ports):
                    #self.mp285_go(self.position_lick)
                    #self.moved_ports = True
            if self.retract_ports and (self.actuator is not None) and (not self.moved_ports):
                    self.actuator.extend()
                    self.moved_ports = True
                
            if self.th.rule_hint_delay and now()-self.last_hint > self.next_hint_interval: #and ((self.retract_ports and self.mp285.is_moving) or (not self.retract_ports)):
                self.stimulator.go(self.th.trial.side)
                self.last_hint = now()
                
                self.next_hint_interval = np.random.normal(*self.hint_interval)
                if self.next_hint_interval<0:
                    self.next_hint_interval = self.hint_interval[0]

            if 'light' in self.go_cue:
                self.light.set(1)
            if 'sound' in self.go_cue and not self.laser_signaled:
                self.speaker.laser()
                self.laser_signaled = True
            
            #if self.mp285.is_moving:
            #    return # DO NOT PROCESS LICKS UNTIL MP285 REACHES DESTINATION
            
            if not self.th.rule_any:
                self.to_phase(PHASE_REWARD)
                return

            if any(self.licks['phase'] == PHASE_LICK) and not self.th.rule_fault:
                self.to_phase(PHASE_REWARD)
                return
            elif any(self.licks['phase'] == PHASE_LICK) and self.th.rule_fault and any(self.licks[(self.licks['phase']==PHASE_LICK) & (self.licks['side']==self.th.trial.side)]):
                self.to_phase(PHASE_REWARD)
                return
            
            # if time is up, to reward phase
            if dt_phase >= ph_dur:
                self.to_phase(PHASE_REWARD)
                return

        # Reward
        elif ph == PHASE_REWARD:
            if 'light' in self.go_cue:
                self.light.set(1) #probably redundant
            
            if self.th.rule_side and any(self.licks[(self.licks['phase']==PHASE_LICK) & (self.licks['side']==-self.th.trial.side+1)]) and not self.rewarded and not self.th.rule_fault:
                # we arrived here after an incorrect lick
                if not self.wrong_signaled:
                    self.speaker.wrong()
                    self.wrong_signaled = True
                    self.do_reward = False
                #self.to_phase(PHASE_ITI) # by commenting it out, the ports sit there even though there's no reward
                #return
        
            # sanity check. cannot reach here if any incorrect licks, ensure that:
            if self.th.rule_side and (not self.th.rule_fault) and self.do_reward==True:
                assert (not any(self.licks[(self.licks['phase']==PHASE_LICK)&(self.licks['side']==-self.th.trial.side+1)]))
        
            # if no licks at all back in lick phase, go straight to ITI
            if self.th.rule_any and not any(self.licks[self.licks['phase']==PHASE_LICK]):
                self.to_phase(PHASE_ITI)
                return
            
            # if allowed multiple choices but only licked wrong side by the time the lick phase had ended
            if self.th.rule_any and self.th.rule_fault and not any(self.licks[(self.licks['phase']==PHASE_LICK) & (self.licks['side']==self.th.trial.side)]):
                self.to_phase(PHASE_ITI)
                return

            # sanity check. can only reach here if licked correct side only
            if self.th.rule_any and self.th.rule_side and self.do_reward:
                assert any(self.licks[(self.licks['side']==self.th.trial.side)&(self.licks['phase']==PHASE_LICK)])
     
            # from this point on, it is assumed that rewarding should occur if do_reward is True (otherwise would either have moved to ITI, or do_reward would now be False)
            
            if self.use_trials:
                rside = self.th.trial.side
            else:
                rside = (self.licks[self.licks['phase']==PHASE_LICK].side)[0]
                
            if self.rewards_on and (not self.rewarded) and self.do_reward:
                self.spout.go(side=rside, scale=self.th.reward_scale)
                self.rewarded = now()
                self.rewards_given += 1
                
            if self.th.rule_hint_reward and now()-self.last_hint > self.next_hint_interval:
                self.stimulator.go(self.th.trial.side)
                self.last_hint = now()
                
                self.next_hint_interval = np.random.normal(*self.hint_interval)
                if self.next_hint_interval<0:
                    self.next_hint_interval = self.hint_interval[0]

            if dt_phase >= ph_dur:
                self.to_phase(PHASE_ITI)
        # ITI
        elif ph == PHASE_ITI:
            #if self.retract_ports and (self.mp285 is not None) and (not self.returned_ports):
            #    self.mp285_go(self.position_stim)
            #    self.returned_ports = True
            if self.retract_ports and (self.actuator is not None) and (not self.returned_ports):
                self.actuator.retract()
                self.returned_ports = True

            self.light.set(0)
            
            if any((self.licks['phase']>PHASE_INTRO) & (self.licks['phase']<PHASE_LICK)) and self.th.rule_phase and not self.error_signaled:
                self.speaker.error()
                self.error_signaled = True
        
            if dt_phase >= ph_dur:
                if self.rewarded or (self.motion_control and self.ar.moving) or (not self.motion_control) or self.session_kill:
                    self.to_phase(PHASE_END)
                else:
                    pass
                return
                    
    def next_trial(self):
        
        self.th.next_trial()
       
        # Phase reset
        self.to_phase(PHASE_INTRO)
        _=self.ar.licked # to clear any residual signal

        # Check for mp285 adjustment
        if self.th.do_adjust_mp285 is not False:
            adj = self.th.do_adjust_mp285
            logging.info('Adjusting MP285, moving to side {}'.format(adj))
            self.mp285.nudge(adj)
        
        # Trial-specific runtime vars
        self.licks = np.zeros((2000,),dtype=[('phase',int),('ts',float),('side',int)])
        self.lick_idx = 0

        # Event trackers
        self.stim_idx = 0
        self.do_reward = True # until determined otherwise
        self.rewarded = False
        self.wrong_signaled = False
        self.error_signaled = False
        self.laser_signaled = False
        self.intro_signaled = False
        self.moved_ports = False
        self.returned_ports = False
        self.stimulated = False
        self.licked_early = False
        self.trial_kill = False
        self.last_hint = -1
        self.next_hint_interval = self.hint_interval[0]

        while self.current_phase != PHASE_END:
            self.run_phase()
       
        # Return value indicating whether another trial is appropriate
        if self.session_kill:
            self.paused = False
            return False
        else:
            return True
    def mp285_go(self, pos):
        threading.Thread(target=self.mp285.goto, args=(pos,)).start()
    def email_update(self):
        p = self.th.history_glob.iloc[-10:].fillna(0)
        ntrials = len(p)
        tim = int((now()-self.session_on)/60.)
        s = 'Subject: {}\nTime: {} mins\nN Trials: {}\nRewards: {}\nLevel: {}\nPerformance:\n{}\n'.format(self.subj.name,tim, ntrials, self.rewards_given, self.th.level, str(p))
        email_alert(s, subject='Rig{}, {}min, {}, {}'.format(config.rig_id, tim, self.subj.name, self.name_as_str()), figure=self.live_figure)
    def run(self):
        try:
            self.session_on = now()
            self.ar.begin_saving()
            self.cam.begin_saving()
            
            self.sic.start_acq()

            cont = True
            last_email = now()-960
            while cont:
                if now()-last_email > (900):
                    threading.Thread(target=self.email_update).start()
                    last_email = now()
                cont = self.next_trial()

            self.sic.stop_acq()
                
            self.end()
        except:
            logging.error('Session has encountered an error!')
            email_alert('Session error!', subject='ERROR! Puffs Interface Alert')
            raise
   
    def end(self):
        self.actuator.saver = None
        to_end = [self.ar, self.stimulator, self.spout, self.light, self.cam, self.opto, self.sic]
        for te in to_end:
            try:
                te.end()
            except:
                warnings.warn('Failed to end one of the processes: {}'.format(str(te)))
            time.sleep(0.100)
        self.saver.end(notes=self.notes)
        self.session_on = False
            
    def get_code(self):
        py_files = [pjoin(d,f) for d,_,fs in os.walk(os.getcwd()) for f in fs if f.endswith('.py') and not f.startswith('__')]
        code = {}
        for pf in py_files:
            with open(pf, 'r') as f:
                code[pf] = f.read()
        return json.dumps(code)
