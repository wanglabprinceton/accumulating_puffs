import threading, wx, time, sys, logging, Queue
import numpy as np
from session import Session
from views import View, MP285View
from subjects import Subject, list_subjects, list_rewards
from settings import manipulations, conditions, manip_strs, default_manipulation
from settings.param_handlers import ParamHandler
from hardware.valve import open_valves, close_valves, give_reward, puff_check
from hardware.mp285 import MP285, set_mp285_home, get_mp285_home
from hardware import LActuator
from util import setup_logging
from util import TCPIP
import config
from settings.constants import *

def pretty_time(t):
    if t<60:
        return '%0.0f s'%t
    else:
        return '%0.0f m, %0.0f s'%(np.floor(t/60.),t%60.)

class Controller:

    REFRESH_INTERVAL = 500 #ms
    STATE_NULL = 0
    STATE_PREPARED = 1
    STATE_RUNNING = 2
    STATE_KILLED_SESSION = 3
    STATE_RUN_COMPLETE = 4

    def __init__(self):
        # Make app
        self.app = wx.App(False) 
        
        self.update_timer = None

        # Generate view    
        subs_list = list_subjects()
        self.cond_list = sorted(conditions.keys())
        self.manip_list = sorted(manipulations.keys())
        self.view = View(None, subs=subs_list, conditions=self.cond_list, manipulations=self.manip_list)
        self.mp285_view = MP285View(None)
        if False:#not config.TESTING_MODE:
            sys.stdout=self.view.redir_out
            sys.stderr=self.view.redir_err
        setup_logging(outwin=self.view.redir_out,errwin=self.view.redir_err)

        self.tcpip = TCPIP(config.scanimage_tcpip_address)
        self.mp285 = MP285(**config.mp285_params)
        self.actuator = LActuator(**config.actuator_params)

        # Button bindings
        self.view.start_button.Bind(wx.EVT_BUTTON, self.evt_onoff)
        self.view.prepare_button.Bind(wx.EVT_BUTTON, self.evt_prepare)
        self.view.pause_button.Bind(wx.EVT_BUTTON, self.evt_pause)
        self.view.tcpip_button.Bind(wx.EVT_BUTTON, self.evt_tcpip)
        self.view.mp285_button.Bind(wx.EVT_BUTTON, self.evt_mp285)
        self.view.resetcam_button.Bind(wx.EVT_BUTTON, self.evt_resetcam)
        self.view.resetlact_button.Bind(wx.EVT_BUTTON, self.evt_resetlact)
        self.view.Bind(wx.EVT_CLOSE, self.evt_close)
        self.view.cal_but.Bind(wx.EVT_BUTTON, self.calib)
        self.view.puffc_but.Bind(wx.EVT_BUTTON, lambda evt: puff_check())
        self.view.locklev_but.Bind(wx.EVT_BUTTON, self.locklev)
        self.view.levu_but.Bind(wx.EVT_BUTTON, lambda evt, temp=1: self.change_level(evt,temp))
        self.view.levd_but.Bind(wx.EVT_BUTTON, lambda evt, temp=-1: self.change_level(evt,temp))
        self.view.rewardl_but.Bind(wx.EVT_BUTTON, lambda evt, temp=L: self.give_reward(evt, temp))
        self.view.rewardr_but.Bind(wx.EVT_BUTTON, lambda evt, temp=R: self.give_reward(evt, temp))
        self.view.puffl_but.Bind(wx.EVT_BUTTON, lambda evt, temp=L: self.give_puff(evt, temp))
        self.view.puffr_but.Bind(wx.EVT_BUTTON, lambda evt, temp=R: self.give_puff(evt, temp))
        self.view.optoon_but.Bind(wx.EVT_BUTTON, self.opto_on)
        self.view.optooff_but.Bind(wx.EVT_BUTTON, self.opto_off)
        self.view.maniptog_but.Bind(wx.EVT_BUTTON, self.manip_toggle)
        self.view.act_ext_but.Bind(wx.EVT_BUTTON, self.actuator_extend)
        self.view.act_ret_but.Bind(wx.EVT_BUTTON, self.actuator_retract)
        self.view.add_sub_button.Bind(wx.EVT_BUTTON, self.evt_addsub)
        self.view.usrinput_box.Bind(wx.EVT_TEXT_ENTER, self.update_usrinput)

        # Button bindings (mp285 view)
        self.mp285_view.Bind(wx.EVT_CLOSE, self.evt_mp285_close)
        self.mp285_view.but_set_home.Bind(wx.EVT_BUTTON, lambda evt, temp='home': self.evt_mp285_set(evt, temp))
        self.mp285_view.but_set_stim.Bind(wx.EVT_BUTTON, lambda evt, temp='stim': self.evt_mp285_set(evt, temp))
        self.mp285_view.but_set_lick.Bind(wx.EVT_BUTTON, lambda evt, temp='lick': self.evt_mp285_set(evt, temp))
        self.mp285_view.but_goto_home.Bind(wx.EVT_BUTTON, lambda evt, temp='home': self.evt_mp285_goto(evt, temp))
        self.mp285_view.but_goto_stim.Bind(wx.EVT_BUTTON, lambda evt, temp='stim': self.evt_mp285_goto(evt, temp))
        self.mp285_view.but_goto_lick.Bind(wx.EVT_BUTTON, lambda evt, temp='lick': self.evt_mp285_goto(evt, temp))
        for direc in self.mp285_view.ctrl_buttons:
            for mag in self.mp285_view.ctrl_buttons[direc]:
                for ax in self.mp285_view.ctrl_buttons[direc][mag]:
                    self.mp285_view.ctrl_buttons[direc][mag][ax].Bind(wx.EVT_BUTTON, lambda evt, temp=(direc,mag,ax): self.evt_mp285_move(evt,temp))


        # Runtime
        self.update_state(self.STATE_NULL)
        self.last_cam_frame = None
        self.n_updates = 0

        # Run
        #self.view.Show()
        self.app.MainLoop()

    def update_state(self, st=None):
        if st is not None:
            self.state = st

        if self.state == self.STATE_NULL:
            self.view.prepare_button.Enable()
            self.view.prepare_button.SetLabel('Prepare Session')
            self.view.add_sub_button.Enable()
            self.view.start_button.Disable()
            self.view.cal_but.Enable()
            self.view.levu_but.Disable()
            self.view.levd_but.Disable()
            self.view.puffr_but.Disable()
            self.view.puffl_but.Disable()
            self.view.rewardr_but.Enable()
            self.view.rewardl_but.Enable()
            self.view.optoon_but.Disable()
            self.view.optooff_but.Disable()
            self.view.maniptog_but.Disable()
            self.view.pause_button.Disable()
            self.view.update_sub_choices(list_rewards())
            self.view.locklev_but.Disable()
            self.mp285_view.but_set_lick.Enable()
            self.mp285_view.but_set_home.Enable()
            self.mp285_view.but_set_stim.Enable()
        elif self.state == self.STATE_PREPARED:
            self.view.usrinput_box.SetValue('(notes)')
            self.view.prepare_button.SetLabel('Cancel Session')
            self.view.prepare_button.Enable()
            self.view.add_sub_button.Disable()
            self.view.cal_but.Disable()
            self.view.start_button.SetLabel("Run Session")
            self.view.start_button.SetBackgroundColour((0,255,0))
            self.view.start_button.Enable()
            self.view.puffr_but.Enable()
            self.view.puffl_but.Enable()
            self.view.optoon_but.Enable()
            self.view.optooff_but.Enable()
            self.view.maniptog_but.Enable()
            self.view.levu_but.Disable()
            self.view.levd_but.Disable()
            self.view.rewardr_but.Enable()
            self.view.rewardl_but.Enable()
            self.view.pause_button.Disable()
            self.view.locklev_but.SetLabel('Lock')
            self.view.locklev_but.Enable()
            self.mp285_view.but_set_lick.Disable()
            self.mp285_view.but_set_home.Disable()
            self.mp285_view.but_set_stim.Disable()
        elif self.state == self.STATE_RUNNING:
            self.view.prepare_button.Disable()
            self.view.prepare_button.SetLabel('Prepare Session')
            self.view.add_sub_button.Disable()
            self.view.cal_but.Disable()
            self.view.start_button.Disable()
            self.view.puffr_but.Enable()
            self.view.puffl_but.Enable()
            self.view.levu_but.Enable()
            self.view.levd_but.Enable()
            self.view.rewardr_but.Enable()
            self.view.rewardl_but.Enable()
            self.view.optoon_but.Enable()
            self.view.optooff_but.Enable()
            self.view.maniptog_but.Enable()
            self.view.start_button.SetLabel('End Session')
            self.view.start_button.SetBackgroundColour((255,0,0))
            self.view.pause_button.Enable()
            self.view.locklev_but.Enable()
            self.mp285_view.but_set_lick.Disable()
            self.mp285_view.but_set_home.Disable()
            self.mp285_view.but_set_stim.Disable()
        elif self.state == self.STATE_KILLED_SESSION:
            self.view.start_button.SetLabel('Ending...')
            self.view.start_button.Disable()
            self.view.cal_but.Disable()
            self.view.puffr_but.Disable()
            self.view.puffl_but.Disable()
            self.view.levu_but.Disable()
            self.view.levd_but.Disable()
            self.view.rewardr_but.Disable()
            self.view.rewardl_but.Disable()
            self.view.optoon_but.Disable()
            self.view.optooff_but.Disable()
            self.view.maniptog_but.Disable()
            self.view.pause_button.Disable()
            self.view.locklev_but.Disable()
            self.mp285_view.but_set_lick.Disable()
            self.mp285_view.but_set_home.Disable()
            self.mp285_view.but_set_stim.Disable()
            if self.session.session_on:
                self.update_timer = wx.CallLater(self.REFRESH_INTERVAL, self.update_state)
            else:
                self.update_state(self.STATE_RUN_COMPLETE)
            
        elif self.state == self.STATE_RUN_COMPLETE:
            pos = get_mp285_home()
            self.mp285.goto(pos)
            self.view.SetTitle('Puffs Experiment Control')
            self.update_timer.Stop()
            self.view.start_button.SetLabel("Run Session")
            self.view.start_button.SetBackgroundColour((0,255,0))
            self.view.prepare_button.Enable()
            self.view.prepare_button.SetLabel('Prepare Session')
            self.view.add_sub_button.Enable()
            self.view.startlevel_box.SetValue('(level override)')
            self.view.cal_but.Enable()
            self.view.start_button.Disable()
            self.view.puffr_but.Disable()
            self.view.puffl_but.Disable()
            self.view.rewardr_but.Enable()
            self.view.rewardl_but.Enable()
            self.view.levu_but.Disable()
            self.view.levd_but.Disable()
            self.view.optoon_but.Disable()
            self.view.optooff_but.Disable()
            self.view.maniptog_but.Disable()
            self.view.pause_button.Disable()
            self.view.update_sub_choices(list_rewards())
            self.view.locklev_but.SetLabel('Lock')
            self.view.locklev_but.Disable()
            self.mp285_view.but_set_lick.Enable()
            self.mp285_view.but_set_home.Enable()
            self.mp285_view.but_set_stim.Enable()
            self.view.imaging_box.SetValue(False)
            self.view.manip_box.SetSelection(0)
            self.view.cond_box.SetSelection(0)
    
    def update(self):
        if (not self.session.session_on) and self.state == self.STATE_RUNNING:
            self.update_state(self.STATE_RUN_COMPLETE)
            return

        # checks
        if self.view.trial_n_widg.GetValue() == str(self.session.th.idx):
            new_trial_flag = False
        else:
            new_trial_flag = True

        # clocks
        self.view.session_runtime_widg.SetValue(pretty_time(self.session.session_runtime))
        self.view.trial_runtime_widg.SetValue(pretty_time(self.session.trial_runtime))

        # plots
        try:
            self.view.set_lick_data(self.session.ar.get_accum())
        except Queue.Empty:
            pass
        except:
            logging.error('Interface could not update lick info.')
            try:
                self.view.fig_lock.release()
            except:
                pass

        # movie 
        cam_frame = self.session.cam.get()
        self.view.set_cam(cam_frame)
        # commented out b/c causes lags
        #if self.last_cam_frame is not None and self.n_updates>60 and cam_frame is not None:
        #    cc = np.corrcoef(cam_frame, self.last_cam_frame)[0,1]
        #    if cc < 0.85:
        #        self.evt_resetcam(None)
        #self.last_cam_frame = cam_frame
        
        # trial
        if new_trial_flag:
            self.update_trial()

        # pauses
        if self.session.paused:
            self.view.pause_button.SetLabel('Unpause')
            self.view.pause_button.SetBackgroundColour((0,255,0))
            self.view.start_button.Disable()
        elif not self.session.paused:
            self.view.pause_button.SetLabel('Pause')
            self.view.pause_button.SetBackgroundColour((0,150,150))
            if self.session.session_on and not self.session.session_kill:
                self.view.start_button.Enable()
        
        self.n_updates += 1
        self.update_timer = wx.CallLater(self.REFRESH_INTERVAL, self.update)

    def update_trial(self):
        try:
            if self.session.th.idx < 0:
                return
            self.view.trial_n_widg.SetValue("%s (%s)"%(str(self.session.th.idx),str(self.session.th.valid_idx)))
            self.view.set_trial_data(self.session.th, self.session)
            self.view.rewarded_widg.SetValue(str(self.session.rewards_given))
            self.view.set_bias(self.session.th.biases)
            self.view.set_manip(manip_strs[self.session.th.manip])
            if self.session.th.idx > 0:
                self.view.set_history(self.session.th)
        except:
            logging.error('Interface could not update trial info.')

    ####### EVENTS ########
    def evt_prepare(self, evt):
        if self.state == self.STATE_PREPARED:
            self.mp285.saver = None
            self.session.end()
            self.update_state(self.STATE_NULL)

        else:
            sel_sub = self.view.sub_box.GetSelection()
            sel_cond = self.view.cond_box.GetSelection()
            sel_manip = self.view.manip_box.GetSelection()
            if wx.NOT_FOUND in [sel_sub,sel_cond,sel_manip]:
                dlg = wx.MessageDialog(self.view, message='Selections not made.', caption='Preparation not performed.', style=wx.OK)
                res = dlg.ShowModal()
                dlg.Destroy()
                return

            sub_name = self.view.sub_names[sel_sub]
            cond_name = self.cond_list[sel_cond]
            manip_name = self.manip_list[sel_manip]
            if manip_name != 'none':
                logging.info('Manipulation: {}'.format(manip_name))
            imaging = self.view.imaging_box.GetValue()
            startlevel = self.view.startlevel_box.GetValue()
            if startlevel == '(level override)':
                startlevel = -1
            try:
                startlevel = int(startlevel)
            except:
                startlevel = -1
                logging.info('Start level not understood. Using default.')

            sub = Subject(sub_name)
            #self.mp285.goto(sub.get_position('stim')) # session can handle this
            ph = ParamHandler(sub, condition=conditions[cond_name], manipulation=manipulations[manip_name], imaging=imaging, start_level=startlevel, position=self.mp285.get_pos().tolist())
            self.session = Session(ph.params, mp285=self.mp285, actuator=self.actuator)
            self.session.live_figure = (self.view.fig,self.view.fig_lock)
            self.mp285.saver = self.session.saver

            # tcpip communication
            if imaging:
                si_path = config.si_data_path+r'\\{}'.format(sub_name)
                seshname = self.session.name_as_str()
                dic = dict(path=si_path, name=seshname, idx=1)
                cont = True
                while cont:
                    suc = self.tcpip.send(dic)
                    if not suc:
                        dlg = wx.MessageDialog(self.view, caption='ScanImage preparation failed.', message='Try again?', style=wx.YES_NO)
                        res = dlg.ShowModal()
                        dlg.Destroy()
                        cont = res==wx.ID_YES
                        if cont:
                            self.evt_tcpip(None)
                    else:
                        cont = False

            self.view.setup_axlick()
            self.view.SetTitle('{} - {} - {}'.format(sub_name,cond_name,manip_name))

            self.update_state(self.STATE_PREPARED)
            self.update()

    def evt_mp285(self, evt):
        self.mp285_view.Show()
        self.mp285_view.SetFocus()
        self.mp285_view.Raise()
    def evt_mp285_close(self, evt):
        evt.Veto()
        self.mp285_view.Hide()
    def evt_mp285_set(self, evt, detail):

        pos = self.mp285.get_pos()

        if detail in ['stim','lick']:
            sel_sub = self.view.sub_box.GetSelection()
            if sel_sub == wx.NOT_FOUND:
                dlg = wx.MessageDialog(self.view, message='No subject selected.', caption='Position not set.', style=wx.OK)
                res = dlg.ShowModal()
                dlg.Destroy()
                return
            
            sub_name = self.view.sub_names[sel_sub]
            sub = Subject(sub_name)
            sub.set_position(pos, kind=detail)
        elif detail == 'home':
            set_mp285_home(pos)
            
    def evt_mp285_goto(self, evt, detail):

        if detail in ['stim','lick']:
            sel_sub = self.view.sub_box.GetSelection()
            if sel_sub == wx.NOT_FOUND:
                dlg = wx.MessageDialog(self.view, message='No subject selected.', caption='Position not set.', style=wx.OK)
                res = dlg.ShowModal()
                dlg.Destroy()
                return
            
            sub_name = self.view.sub_names[sel_sub]
            sub = Subject(sub_name)
            pos = sub.get_position(kind=detail)
            self.mp285.goto(pos)
        elif detail == 'home':
            pos = get_mp285_home()
            self.mp285.goto(pos)
            
    def evt_mp285_move(self, evt, detail):
        direc,mag,ax = detail
        change = np.zeros(3)
        spot = dict(x=0,y=1,z=2)[ax]
        sign = dict(up=1,down=-1)[direc]
        change[spot] += sign*float(mag)

        curpos = self.mp285.get_pos()
        pos = curpos + change
        self.mp285.goto(pos)

    def evt_resetcam(self, evt):
        if self.state != self.STATE_RUNNING:
            return
        self.session.cam.reset_cams()
        
    def evt_resetlact(self, evt):
        logging.info('Resetting actuator...')
        self.actuator.end()
        self.actuator = LActuator(**config.actuator_params)
        
    def evt_tcpip(self, evt):
        bi = wx.BusyInfo('Connecting TCPIP; click connect on remote machine...', self.view)
        suc = self.tcpip.reconnect()
        bi.Destroy()
        if not suc:
            dlg = wx.MessageDialog(self.view, caption='TCPIP reconnection failed.', message='TCPIP not active.', style=wx.OK)
            res = dlg.ShowModal()
            dlg.Destroy()
        else:
            logging.info('TCPIP connected.')

    def evt_onoff(self, evt):
        #if self.state!=self.STATE_RUNNING and self.state!=self.STATE_PREPARED,:
        #    dlg = wx.MessageDialog(self.view, message='', caption='No session prepared.', style=wx.OK)
        #    res = dlg.ShowModal()
        #    dlg.Destroy()
        #    return
        if self.state != self.STATE_RUNNING:
            self.update_state(self.STATE_RUNNING)
            self.run_th = threading.Thread(target=self.session.run)
            self.run_th.start()
        elif self.state == self.STATE_RUNNING:
            # store log in session data
            self.mp285.saver = None
            self.session.notes['stdout'] = self.view.redir_out.text_ctrl.GetValue()
            self.session.notes['stderr'] = self.view.redir_err.text_ctrl.GetValue()
            self.session.session_kill = True
            self.update_state(self.STATE_KILLED_SESSION)

    def evt_pause(self, evt):
        if not self.session.paused:
            self.session.pause(True)
            self.view.pause_button.SetLabel('Unpause')
            self.view.pause_button.SetBackgroundColour((0,255,0))
            self.view.start_button.Disable()
        elif self.session.paused:
            self.session.pause(False)
            self.view.pause_button.SetLabel('Pause')
            self.view.pause_button.SetBackgroundColour((0,100,200))
            self.view.start_button.Enable()

    def evt_close(self, evt):
        if self.state in [self.STATE_RUNNING]:
            dlg = wx.MessageDialog(self.view, message='End session before closing interface.', caption='Session is active.', style=wx.OK)
            res = dlg.ShowModal()
            dlg.Destroy()
            evt.Veto()
        elif self.state in [self.STATE_NULL, self.STATE_RUN_COMPLETE, self.STATE_PREPARED]:
            dlg = wx.MessageDialog(self.view, message="", caption="Exit Experiment?", style=wx.OK|wx.CANCEL)
            result = dlg.ShowModal()
            dlg.Destroy()
            if result == wx.ID_OK:
                if self.state == self.STATE_PREPARED:
                    self.session.end()
                    self.update_state(self.STATE_KILLED_SESSION)
                    while self.state != self.STATE_RUN_COMPLETE:
                        pass
                if self.update_timer is not None:
                    self.update_timer.Stop()
                self.mp285.end()
                self.actuator.end()
                self.tcpip.end()
                self.mp285_view.Destroy()
                self.view.Destroy()
            else:
                evt.Veto()

    def evt_addsub(self, evt):
        dlg = wx.TextEntryDialog(self.view, message='Enter new subject name:')
        ret = dlg.ShowModal()
        if ret == wx.ID_OK:
            self.view.add_sub(dlg.GetValue().strip().lower(), rewards=list_rewards())
        else:
            pass

    def give_reward(self, evt, side):
        if self.state in [self.STATE_RUNNING,self.STATE_PREPARED]:
            self.session.spout.go(side)
        else:
            give_reward(side)
        logging.info('Manual reward given.')
    def give_puff(self, evt, side):
        self.session.stimulator.go(side)
        logging.info('Manual puff given.')
    def change_level(self, evt, inc):
        self.session.th.change_level(inc)
    def calib(self,evt):
        if self.view.cal_but.GetLabel() == 'OPEN':
            open_valves()
            self.view.cal_but.SetLabel('CLOSE')
        elif self.view.cal_but.GetLabel() == 'CLOSE':
            close_valves()
            self.view.cal_but.SetLabel('OPEN')
        
    def locklev(self, evt):
        if self.session.th.level_locked:
            self.session.th.level_locked = False
            self.view.locklev_but.SetLabel('Lock')
            logging.info('Level unlocked.')
        elif not self.session.th.level_locked:
            self.session.th.level_locked = True
            self.view.locklev_but.SetLabel('Unlock')
            logging.info('Level locked.')
    def opto_on(self, evt):
        self.session.opto.set(1)
    def opto_off(self, evt):
        self.session.opto.set(0)
    def manip_toggle(self, evt):
        if self.session.th.force_manip is None: # Disable manip
            self.session.th.force_manip = default_manipulation
            self.view.maniptog_but.SetLabel('ENABLE')
            logging.info('Manipulation disabled.')
        elif self.session.th.force_manip is not None: # Enable manip
            self.session.th.force_manip = None
            self.view.maniptog_but.SetLabel('DISABLE')
            logging.info('Manipulation enabled.')
    def actuator_extend(self, evt):
        self.actuator.extend()
    def actuator_retract(self, evt):
        self.actuator.retract()
            
    def update_usrinput(self, evt):
        self.session.notes['notes'] = self.view.usrinput_box.GetValue()
        logging.info('Metadata updated.')
