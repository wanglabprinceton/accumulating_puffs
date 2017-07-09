import numpy as np
from util import now, email_alert
import pandas as pd
import logging
from settings.rules import *
from settings.constants import *

class TrialHandler(object):

    def __init__(self, saver=None, levels=None, rate_sum=None, stim_duration=None, stim_phase_duration=None, delay_phase_duration=None, stim_phase_pad=None, min_isi=None, alternate_training_levels=False, bias_correction=None, max_bias_correction=None, min_bias_for_correction=None, condition=None, start_level=-1, reward_scaling_threshold=None, antibias_reward_scales=None, mp285_adjust_threshold=None, mp285_adjust_nthreshold=None, mp285_adjust_max_adjusts=None):

        # Params
        self.saver = saver
        self.rate_sum = rate_sum
        self.stim_duration = stim_duration
        self.stim_phase_duration = stim_phase_duration # choices, probabilities
        self.delay_phase_duration = delay_phase_duration
        self.stim_phase_pad = stim_phase_pad
        self.min_isi = min_isi
        self.alternate_training_levels = alternate_training_levels
        self.bias_correction = bias_correction
        self.max_bias_correction = max_bias_correction
        self.min_bias_for_correction = min_bias_for_correction
        self.condition = condition
        self.start_level = start_level
        self.reward_scaling_threshold = reward_scaling_threshold
        self.antibias_reward_scales = antibias_reward_scales
        self.mp285_adjust_threshold = mp285_adjust_threshold
        self.mp285_adjust_nthreshold = mp285_adjust_nthreshold
        self.mp285_adjust_max_adjusts = mp285_adjust_max_adjusts
       
        # Setup levels
        self.setup_levels(levels)

        # Storage
        self.trials = pd.DataFrame(columns=['idx','start','end','dur','ratio','nL','nR','nL_intended','nR_intended','side','condition','manipulation','outcome','reward','delay','rule','level','reward_scale','draw_p'])
        self.trials_timing = pd.DataFrame(columns=['trial','side','time'])
        
        # Runtime vars
        self.history_glob = pd.DataFrame(columns=['perc','valid','perc_l','perc_r','valid_l','valid_r','outcome','side'])
        self.history_win = pd.DataFrame(columns=['perc','valid','perc_l','perc_r','valid_l','valid_r','outcome','side'])
        self.biases = [-1,-1]
        self.valid_idx = 0 # the current trial index, ignoring all trials that were invalid
        self.level_locked = False
        self.sent_email = False
        self.force_manip = None
        self.current_draw_p = .5
        self.mp285_adjust_trial_counter = 0
        self.mp285_adjusts_counter = 0
        self.do_adjust_mp285 = False # False, 0, 1, where 0/1 mean bias is on that side, so move in that direction (left bias=0, in which case you'd move left)

    @property
    def trial(self):
        return self.trials.iloc[-1]

    @property
    def phase_dur(self):
        # Used to specify to a session how long it should allocate for the phase that presents this trial
        return self.trial.dur + np.sum(self.stim_phase_pad)

    @property
    def delay_dur(self):
        return self.trial.delay

    @property
    def reward_scale(self):
        return self.trial.reward_scale
        
    @property
    def idx(self):
        return len(self.trials)-1

    @property
    def rule_any(self):
        return rules[self.trial.rule][RULEI_ANY]
    @property
    def rule_side(self):
        return rules[self.trial.rule][RULEI_SIDE]
    @property
    def rule_phase(self):
        return rules[self.trial.rule][RULEI_PHASE]
    @property
    def rule_fault(self):
        # answers: "am I allowed faults?"
        return rules[self.trial.rule][RULEI_FAULT]
    @property
    def rule_hint_delay(self):
        return rules[self.trial.rule][RULEI_HINTDELAY]
    @property
    def rule_hint_reward(self):
        return rules[self.trial.rule][RULEI_HINTREWARD]
    @property
    def manip(self):
        return self.trial.manipulation

    def setup_levels(self, levels):
        self.levels = levels

        self.past = self.saver.past_trials
        if self.start_level != -1 and self.start_level>=0:
            self.level = self.start_level
            logging.info('Manual destination level selection: {}'.format(self.level))
        elif self.past is not None:
            self.level = int(self.past.iloc[-1].level)
            if self.level >= len(self.levels): #only occurs when I change level structure mid training
                self.level = len(self.levels)-1
            logging.info('Last detected level: {}'.format(self.level))
        else:
            self.level = 0
        self.destination_level = self.level
        logging.info('Destination level: {}'.format(self.destination_level))
        intro_params = self.levels[self.destination_level]['intro']
        if len(intro_params) == 0:
            self.in_intro = False
        else:
            self.in_intro = 0
            logging.info('Starting on level: {}'.format(intro_params[self.in_intro][0]))

    def change_level(self, inc):
        if self.level_locked:
            logging.info('Level locked, no adjustment made.')
            return
        lev = self.level + inc
        if lev > len(self.levels)-1:
            lev = len(self.levels)-1
        if lev < 0:
            lev = 0
        self.level = lev
        was_int = self.in_intro
        self.in_intro = False
        logging.info('Manually changed to level {}.'.format(self.level))
        if was_int:
            logging.info('Intro progression no longer applies.')

    def update_level(self):
        if self.level_locked:
            return
            
        # if on last level:
        if (self.in_intro is False) and (self.level == len(self.levels)-1):
            return
            
        # at current level: gather all valid trials, all contiguous trials, and all valid contiguous trials
        allvtri = self.trials[(self.trials.outcome.isin([COR,INCOR])) & (self.trials.level==self.level)]
        most_recent_noncur_level = np.argwhere(self.trials.level != self.level).squeeze()
        # bc didnt have time to debug
        try:
            dbval = len(most_recent_noncur_level) == 0
        except:
            dbval = True
        if (not np.any(most_recent_noncur_level)) or dbval:
            contig_tri = self.trials
        else:
            most_recent_noncur_level = most_recent_noncur_level[-1]
            contig_tri = self.trials.iloc[most_recent_noncur_level+1:]  # trials of contiguous level to most recent
        contig_vtri = contig_tri[contig_tri.outcome.isin([COR,INCOR])]
        
        if self.in_intro is not False:
            intro_params = self.levels[self.destination_level]['intro'][self.in_intro]
            self.level = intro_params[0]
            intron = intro_params[1]
            cri = dict(win=intron, n=intron, perc=0, bias=1.0, valid=0)
        else:
            cri = self.levels[self.level]['criteria'] 
            if (self.past is not None) and (len(self.past)) and (self.past.iloc[-1].level==self.level):
                allvtri = pd.concat([self.past, allvtri], ignore_index=True, axis=0)
        
        # check n requirement
        if len(allvtri) < cri['n']:
            return
            
        # check win requirement
        if len(contig_vtri) < cri['win']:
            return

        # window of trials to use for coming criteria
        win_alltri = contig_tri.iloc[-cri['win']:]
        win_valtri = contig_vtri.iloc[-cri['win']:] # window of valid trials

        # check % requirement
        pc = win_valtri.outcome.mean()
        if pc < cri['perc']:
            return

        # check bias requirement
        perc_l = win_valtri[win_valtri.side==L].outcome.mean()
        perc_r = win_valtri[win_valtri.side==R].outcome.mean()
        bi = np.array([perc_l,perc_r])
        bi /= np.sum(bi)
        if np.max(bi) > cri['bias']:
            return

        # check validity requirement
        val = win_alltri.outcome.isin([COR,INCOR]).mean()
        if val < cri['valid']:
            return

        # if all criteria passed:
        if self.in_intro is not False:
            self.in_intro += 1
            if self.in_intro >= len(self.levels[self.destination_level]['intro']):
                self.in_intro = False
                logging.info('Graduated from intro to level {}.'.format(self.destination_level))
                self.level = self.destination_level
            else:
                intro_params = self.levels[self.destination_level]['intro'][self.in_intro]
                self.level = intro_params[0]
                logging.info('Auto-advanced to intro part {}: level {}.'.format(self.in_intro,self.levels[self.destination_level]['intro'][self.in_intro][0]))
        elif self.in_intro is False:
            self.level += 1
            logging.info('Auto-advanced to level {}.'.format(self.level))

    def _next_ratio(self):
        ratio = self.levels[self.level]['ratio']
        if any([isinstance(ratio, dt) for dt in [float, int]]):
            return ratio
        elif isinstance(ratio, list):
            return np.random.choice(ratio)
    def _next_rule(self):
        return self.levels[self.level]['rule']
    def _next_stereo(self):
        return self.levels[self.level]['stereo']
    def _next_manip(self):
        if self.force_manip is not None:
            return self.force_manip
        manip = self.levels[self.level]['manip']
        if isinstance(manip, (float,int)):
            return manip
        elif isinstance(manip, list):
            return np.random.choice(manip[0], p=manip[1])

    def _next_side(self):
        rand = np.random.choice([L, R])
        self.current_draw_p = .5

        if (self.levels[self.level]['alternate'] is True) or (self.in_intro is not False and self.alternate_training_levels==True and self.levels[self.level]['is_training']==True):
            return [L,R][int(self.idx%2==0)]
        
        # If bias correction is off
        if not self.bias_correction:
            return rand

        # if in intro, be sure not to deliver many same-side trials in a row
        if (self.in_intro is not False) and len(self.trials)>2:
            sides = self.trials.iloc[-3:].side.values
            if np.all(sides==sides[0]):
                return L if sides[0] == R else R    
            
        valid_trials = self.trials[self.trials['outcome'].isin([COR,INCOR])]

        # If not enough trials
        if np.sum(valid_trials['side']==L) < self.bias_correction or np.sum(valid_trials['side']==R) < self.bias_correction:
            return rand
        
        perc_l = np.mean(valid_trials[valid_trials['side']==L][-self.bias_correction:]['outcome'])
        perc_r = np.mean(valid_trials[valid_trials['side']==R][-self.bias_correction:]['outcome'])
        percs = np.array([perc_l,perc_r])
       
        # If no bias exists
        if perc_l==perc_r:
            self.biases = [0.5,0.5]
            return rand
            
        self.biases = percs/np.sum(percs)
        if np.min(self.biases) <= self.max_bias_correction:
            argmin = np.argmin(self.biases)
            self.biases[argmin] = self.max_bias_correction
            self.biases[-argmin+1] = 1-self.max_bias_correction
            
        if max(self.biases)<self.min_bias_for_correction:
            return rand
        
        self.current_draw_p = self.biases[0]
        return np.random.choice([L,R], p=self.biases[::-1])
    
    def _next_stimphase_dur(self):
        levdur = self.levels[self.level]['stim_phase_dur']
        if levdur is None:
            levdur = self.stim_phase_duration
        d = np.random.choice(levdur[0], p=levdur[1])
        return d
    def _next_delay(self):
        levdur = self.levels[self.level]['delay_phase_dur']
        if levdur is None:
            levdur = self.delay_phase_duration

        d = np.random.choice(levdur[0], p=levdur[1])
        return d
    def _next_reward_scale(self, side):
        minbias = np.min(self.biases)
        if minbias>self.reward_scaling_threshold or minbias==-1:
            return 1.0
        else:
            badside = np.argmin(self.biases)
            if badside != side:
                return 1.0
            else:
                return np.random.choice(self.antibias_reward_scales)
    def _check_adjust_mp285(self):
        if self.levels[self.level]['mp285_adjust_on'] is False:
            return False
        minbias = np.min(self.biases)
        if minbias > self.mp285_adjust_threshold or minbias==-1:
            self.mp285_adjust_trial_counter = 0
            return False
        self.mp285_adjust_trial_counter += 1
        if self.mp285_adjust_trial_counter >= self.mp285_adjust_nthreshold:
            goodside = np.argmax(self.biases)
            inc = {0:-1, 1:1}[goodside]
            if np.abs(self.mp285_adjusts_counter + inc) >= self.mp285_adjust_max_adjusts:
                return False
        
            # if reached here, adjustment will occur (otherwise won't)
            self.mp285_adjust_trial_counter = 0
            self.mp285_adjusts_counter += inc
            
            return goodside
        else:
            return False
    def next_trial(self):
        self.email()
        side = self._next_side()
        self.update_level()
        ratio = self._next_ratio()
        rule = self._next_rule()
        stereo = self._next_stereo()
        manip = self._next_manip()
        dur = self._next_stimphase_dur() 
        delay = self._next_delay()
        reward_scale = self._next_reward_scale(side)
        self.do_adjust_mp285 = self._check_adjust_mp285() # if this is 0, move leftward (to eliminate left bias)

        self.trt,final_lam = self._generate_trial(side, ratio, dur, stereo)
        final_ratio = final_lam[R]/final_lam[L]
        panda_trt = pd.DataFrame(self.trt)
        panda_trt['trial'] = len(self.trials)
        self.saver.write('trials_timing', panda_trt)

        self.trials.loc[len(self.trials)] = pd.Series(dict(start=now(), ratio=final_ratio, side=side, dur=dur, nL_intended=np.sum(self.trt['side']==L), nR_intended=np.sum(self.trt['side']==R), condition=self.condition, idx=len(self.trials), delay=delay, rule=rule, level=float(self.level), manipulation=manip, reward_scale=reward_scale, draw_p=self.current_draw_p ))

    def end_trial(self, outcome, rew, nLnR):
        # Save trial
        self.trials.iloc[-1]['end'] = now()
        self.trials.iloc[-1]['outcome'] = outcome
        self.trials.iloc[-1]['reward'] = rew
        self.trials.iloc[-1]['nL'] = nLnR[L]
        self.trials.iloc[-1]['nR'] = nLnR[R]
        self.saver.write('trials',self.trials.iloc[-1].to_dict())

        if outcome in [COR,INCOR]:
            self.valid_idx += 1

        self.update_history()
    def email(self):
        if self.sent_email:
            return
        if len(self.trials) < 6:
            return
        else:
            ro = self.trials.iloc[-6:].outcome.values
            if not np.any(ro<2):
                email_alert('6 outcomes have been invalid. Check on rig.', subject='PUFFS: STRANGE OUTCOMES')
                self.sent_email = True
    def update_history(self, win=15):    
        # GLOB
        ivalid = self.trials['outcome'].isin([COR,INCOR])
        if ivalid.sum() == 0:
            perc, perc_l, perc_r, valid, valid_l, valid_r = 0,0,0,0,0,0
        else:
            perc = self.trials.ix[ivalid]['outcome'].mean()
            perc_l = self.trials.ix[(ivalid) & (self.trials['side']==L)]['outcome'].mean()
            perc_r = self.trials.ix[(ivalid) & (self.trials['side']==R)]['outcome'].mean()
            valid = ivalid.mean()
            if (self.trials.side==L).sum() > 0:
                valid_l = ((ivalid) & (self.trials.side==L)).sum() / float((self.trials.side==L).sum())
            else:
                valid_l = np.nan
            if (self.trials.side==R).sum() > 0:
                valid_r = ((ivalid) & (self.trials.side==R)).sum() / float((self.trials.side==R).sum())
            else:
                valid_r = np.nan
        self.history_glob.loc[len(self.history_glob)] = pd.Series(dict(perc=perc, perc_l=perc_l, perc_r=perc_r, valid=valid, valid_l=valid_l, valid_r=valid_r, outcome=self.trials['outcome'].iloc[-1], side=self.trials['side'].iloc[-1]))
        
        # WIN
        if win>=len(self.trials):
            wtri = self.trials
        else:
            wtri = self.trials.iloc[-win:]
        ivalid = wtri['outcome'].isin([COR,INCOR])
        if ivalid.sum() == 0:
            perc, perc_l, perc_r, valid, valid_l, valid_r = 0,0,0,0,0,0
        else:
            perc = wtri.ix[ivalid]['outcome'].mean()
            perc_l = wtri.ix[(ivalid) & (wtri['side']==L)]['outcome'].mean()
            perc_r = wtri.ix[(ivalid) & (wtri['side']==R)]['outcome'].mean()
            valid = ivalid.mean()
            if (wtri.side==L).sum() > 0:
                valid_l = ((ivalid) & (wtri.side==L)).sum() / float((wtri.side==L).sum())
            else:
                valid_l = np.nan
            if (wtri.side==R).sum() > 0:
                valid_r = ((ivalid) & (wtri.side==R)).sum() / float((wtri.side==R).sum())
            else:
                valid_r = np.nan
        self.history_win.loc[len(self.history_win)] = pd.Series(dict(perc=perc, perc_l=perc_l, perc_r=perc_r, valid=valid, valid_l=valid_l, valid_r=valid_r, outcome=wtri['outcome'].iloc[-1], side=wtri['side'].iloc[-1]))
                
    def _generate_trial(self, side, ratio, dur, stereo):
        np.seterr(divide='ignore')

        # determine rate parameters for both sides
        lam = self.rate_sum/(ratio + 1)
        lam = np.array([lam, self.rate_sum-lam])
        assert np.sum(lam) == self.rate_sum
        assert round(lam[0]/lam[1],10)==round(ratio,10) or round(lam[1]/lam[0],10)==round(ratio,10)
        beta = 1./lam

        def generate_train(b,dur,isi):
            times = []
            
            # determine when to stop generating stimuli, based on whether there will be stereo at end
            if stereo[-1] == True:
                et = dur-isi
            elif stereo[-1] == False:
                et = dur
                    
            while True:
                to_add = np.random.exponential(b)

                ## This is the simplest approach for enforcing inter-stimulus intervals, but can lead to non-randomness if rate_sum is too high relative to min_isi
                if to_add<isi:
                    to_add = isi

                if sum(times)+to_add >= et:
                    break

                times.append(to_add)
            return np.cumsum(times)

        # generate event times
        timesL,timesR = [],[]
        while len(timesL) == len(timesR):
            timesL,timesR = [generate_train(b,dur,self.min_isi) for b in beta]
        if stereo[0]:
            timesL,timesR = np.append(0,timesL),np.append(0,timesR) # first 2 puffs
        if stereo[1]:
            timesL,timesR = np.append(timesL,dur),np.append(timesR,dur) # last 2 puffs
        
        # build trial matrix
        sides = np.concatenate([np.zeros(len(timesL)), np.ones(len(timesR))])
        times = np.concatenate([timesL, timesR])
        trial = np.zeros(len(sides), dtype=[('side',int),('time',float)])
        trial['side'] = sides
        trial['time'] = times
        trial = trial[np.argsort(trial['time'])]
        if stereo[0] and np.random.random()<0.5:
            trial[:2]['side'] = -trial[:2]['side']+1 # in case of systematic timing error, first one will be random
        if stereo[1] and np.random.random()<0.5:
            trial[-2:]['side'] = -trial[-2:]['side']+1 # in case of systematic timing error, last one will be random

        # sanity checks
        assert np.all(trial['time']<=dur)
        assert np.all(np.round(np.diff(trial[trial['side']==0]['time']), 4) >= self.min_isi)
        assert np.all(np.round(np.diff(trial[trial['side']==1]['time']), 4) >= self.min_isi)

        # add intro
        if stereo[0]:
            trial['time'][2:] += self.stim_phase_pad[0]

        # construct trial object
        trial_obj = np.array(trial, dtype=[('side',int),('time',float)])

        # adjust for correct side
        curcor = np.round(np.mean(trial_obj['side']))
        if curcor != side:
            trial_obj['side'] = -trial_obj['side']+1
            lam = lam[::-1]

        # sanity checks
        if stereo[0]:
            assert np.all(trial_obj['time'][:2]==[0.,0.])
        if stereo[1]:
            assert np.all(trial_obj['time'][-2:]==[dur+self.stim_phase_pad[0],dur+self.stim_phase_pad[0]])

        return trial_obj,lam
    
    def get_cum_performance(self, n=None):
        cum = np.asarray(self.trial_outcomes)
            
        markers = cum.copy()
        if self.lick_rule_phase:
            ignore = [EARLY_L,EARLY_R,NULL,KILLED]
        else:
            ignore = [NULL,KILLED]
        valid = np.array([c not in ignore for c in cum]).astype(bool)
        cum = cum==COR
        if n is None:
            cum = [np.mean([c for c,v in zip(cum[:i],valid[:i]) if v]) if np.any(valid[:i]) else 0. for i in xrange(1,len(cum)+1)] #cumulative
        else:
            cum = [np.mean([c for c,v in zip(cum[max([0,i-n]):i],valid[max([0,i-n]):i]) if v]) if np.any(valid[max([0,i-n]):i]) else 0. for i in xrange(1,len(cum)+1)] #cumulative
        return cum,markers,np.asarray(self.trial_corrects)
