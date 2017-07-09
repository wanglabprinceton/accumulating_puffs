import numpy as np
from matplotlib.figure import Figure
import matplotlib.gridspec as gridspec
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg
import matplotlib.cm as cm
import logging, wx, threading

class RedirectText(object):
    def __init__(self, text_ctrl):
        self.text_ctrl = text_ctrl
    def write(self, s):
        wx.CallAfter(self.text_ctrl.WriteText, s)

### Wx ###
class View(wx.Frame):
    def __init__(self, parent, subs=[], conditions=[], manipulations=[], size=(1400,830)):
        wx.Frame.__init__(self, parent, title="Puffs Experiment Control", size=size)
        self.Center()
        
        self.n_perf_show = 50
        self.n_lick_show = 1200
        self.fig_lock = threading.Lock()
        
        # Leftmost panel
        self.panel_left_sizer = wx.BoxSizer(wx.VERTICAL)
        self.add_sub_button = wx.Button(self, label='Add Subject')
        self.sub_box = wx.ListBox(self)
        self.sub_names,self.sub_strs = subs,[]
        self.update_sub_choices()
        self.cond_box = wx.ListBox(self, choices=conditions)
        self.manip_box = wx.ListBox(self, choices=manipulations)
        self.imaging_box = wx.CheckBox(self, label='Imaging')
        self.startlevel_box = wx.TextCtrl(self, wx.ID_ANY, value='(level override)')
        self.panel_left_sizer.Add(self.imaging_box)
        self.panel_left_sizer.Add(self.startlevel_box)
        self.panel_left_sizer.Add(self.add_sub_button)
        self.panel_left_sizer.Add(self.sub_box, flag=wx.EXPAND|wx.ALL, proportion=1)
        self.panel_left_sizer.Add(self.cond_box, flag=wx.EXPAND|wx.ALL, proportion=1)
        self.panel_left_sizer.Add(self.manip_box, flag=wx.EXPAND|wx.ALL, proportion=1)

        # top panel
        self.panel_top = wx.Panel(self,1)
        self.panel_top_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.trial_n_widg = wx.TextCtrl(self.panel_top)
        self.trial_n_widg.SetEditable(False)
        self.trial_n_lab = wx.StaticText(self.panel_top, label='Trial #: ', style=wx.ALIGN_RIGHT)
        self.session_runtime_widg = wx.TextCtrl(self.panel_top)
        self.session_runtime_widg.SetEditable(False)
        self.session_runtime_lab = wx.StaticText(self.panel_top, label='Session time: ', style=wx.ALIGN_RIGHT)
        self.trial_runtime_widg = wx.TextCtrl(self.panel_top)
        self.trial_runtime_widg.SetEditable(False)
        self.trial_runtime_lab = wx.StaticText(self.panel_top, label='Trial time: ', style=wx.ALIGN_RIGHT)
        self.rewarded_widg = wx.TextCtrl(self.panel_top)
        self.rewarded_widg.SetEditable(False)
        self.rewarded_lab = wx.StaticText(self.panel_top, label='Rewards: ', style=wx.ALIGN_RIGHT)
        self.bias_widg = wx.TextCtrl(self.panel_top)
        self.bias_widg.SetEditable(False)
        self.bias_lab = wx.StaticText(self.panel_top, label='RL Bias: ', style=wx.ALIGN_RIGHT)
        self.manip_lab = wx.StaticText(self.panel_top, label='Manip: ', style=wx.ALIGN_RIGHT)
        self.manip_widg = wx.TextCtrl(self.panel_top)
        self.manip_widg.SetEditable(False)
        self.panel_top_sizer.Add(self.trial_n_lab, flag=wx.ALIGN_RIGHT, proportion=1)
        self.panel_top_sizer.Add(self.trial_n_widg, flag=wx.EXPAND|wx.ALL, proportion=1)
        self.panel_top_sizer.Add(self.session_runtime_lab, flag=wx.ALIGN_RIGHT, proportion=1)
        self.panel_top_sizer.Add(self.session_runtime_widg, flag=wx.EXPAND|wx.ALL, proportion=1)
        self.panel_top_sizer.Add(self.trial_runtime_lab, flag=wx.ALIGN_RIGHT, proportion=1)
        self.panel_top_sizer.Add(self.trial_runtime_widg,flag=wx.EXPAND|wx.ALL, proportion=1)
        self.panel_top_sizer.Add(self.rewarded_lab, flag=wx.ALIGN_RIGHT, proportion=1)
        self.panel_top_sizer.Add(self.rewarded_widg,flag=wx.EXPAND|wx.ALL, proportion=1)
        self.panel_top_sizer.Add(self.bias_lab, flag=wx.ALIGN_RIGHT, proportion=1)
        self.panel_top_sizer.Add(self.bias_widg,flag=wx.EXPAND|wx.ALL, proportion=1)
        self.panel_top_sizer.Add(self.manip_lab, flag=wx.ALIGN_RIGHT, proportion=1)
        self.panel_top_sizer.Add(self.manip_widg,flag=wx.EXPAND|wx.ALL, proportion=1)
        self.panel_top.SetSizerAndFit(self.panel_top_sizer)
        
        # 2nd from top panel
        self.panel_top2 = wx.Panel(self)
        self.panel_top2_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.cal_lab = wx.StaticText(self.panel_top2, label='Spouts: ', style=wx.ALIGN_RIGHT)
        self.cal_but = wx.Button(self.panel_top2, label='OPEN')
        self.locklev_lab = wx.StaticText(self.panel_top2, label='Lock level: ', style=wx.ALIGN_RIGHT)
        self.locklev_but = wx.Button(self.panel_top2, label='Lock')
        self.lev_lab = wx.StaticText(self.panel_top2, label='Change level: ', style=wx.ALIGN_RIGHT)
        self.levu_but = wx.Button(self.panel_top2, label='UP')
        self.levd_but = wx.Button(self.panel_top2, label='DOWN')
        self.reward_lab = wx.StaticText(self.panel_top2, label='Give reward: ', style=wx.ALIGN_RIGHT)
        self.rewardl_but = wx.Button(self.panel_top2, label='L')
        self.rewardr_but = wx.Button(self.panel_top2, label='R')
        self.act_lab = wx.StaticText(self.panel_top2, label='Actuator: ', style=wx.ALIGN_RIGHT)
        self.act_ext_but = wx.Button(self.panel_top2, label='OUT')
        self.act_ret_but = wx.Button(self.panel_top2, label='IN')
        self.puff_lab = wx.StaticText(self.panel_top2, label='Give puff: ', style=wx.ALIGN_RIGHT)
        self.puffl_but = wx.Button(self.panel_top2, label='L')
        self.puffr_but = wx.Button(self.panel_top2, label='R')
        self.opto_lab = wx.StaticText(self.panel_top2, label='Opto: ', style=wx.ALIGN_RIGHT)
        self.optoon_but = wx.Button(self.panel_top2, label='ON')
        self.optooff_but = wx.Button(self.panel_top2, label='OFF')
        self.maniptog_lab = wx.StaticText(self.panel_top2, label='Manip: ', style=wx.ALIGN_RIGHT)
        self.maniptog_but = wx.Button(self.panel_top2, label='DISABLE')
        self.panel_top2_sizer.Add(self.cal_lab, flag=wx.ALIGN_RIGHT, proportion=1)
        self.panel_top2_sizer.Add(self.cal_but, proportion=1)
        self.panel_top2_sizer.Add(self.locklev_lab, flag=wx.ALIGN_RIGHT, proportion=1)
        self.panel_top2_sizer.Add(self.locklev_but, proportion=1)
        self.panel_top2_sizer.Add(self.lev_lab, flag=wx.ALIGN_RIGHT, proportion=1)
        self.panel_top2_sizer.Add(self.levu_but, proportion=1)
        self.panel_top2_sizer.Add(self.levd_but, proportion=1)
        self.panel_top2_sizer.Add(self.reward_lab, flag=wx.ALIGN_RIGHT, proportion=1)
        self.panel_top2_sizer.Add(self.rewardl_but, proportion=1)
        self.panel_top2_sizer.Add(self.rewardr_but, proportion=1)
        self.panel_top2_sizer.Add(self.act_lab, flag=wx.ALIGN_RIGHT, proportion=1)
        self.panel_top2_sizer.Add(self.act_ext_but, proportion=1)
        self.panel_top2_sizer.Add(self.act_ret_but, proportion=1)
        self.panel_top2_sizer.Add(self.puff_lab, flag=wx.ALIGN_RIGHT, proportion=1)
        self.panel_top2_sizer.Add(self.puffl_but, proportion=1)
        self.panel_top2_sizer.Add(self.puffr_but, proportion=1)
        self.panel_top2_sizer.Add(self.opto_lab, flag=wx.ALIGN_RIGHT, proportion=1)
        self.panel_top2_sizer.Add(self.optoon_but, proportion=1)
        self.panel_top2_sizer.Add(self.optooff_but, proportion=1)
        self.panel_top2_sizer.Add(self.maniptog_lab, flag=wx.ALIGN_RIGHT, proportion=1)
        self.panel_top2_sizer.Add(self.maniptog_but, proportion=1)
        self.panel_top2.SetSizerAndFit(self.panel_top2_sizer)

        # bottom panel
        self.panel_bottom = wx.Panel(self,2)
        self.panel_bottom_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.start_button = wx.Button(self.panel_bottom, label="Run Session")
        self.start_button.SetBackgroundColour((0,255,0))
        self.pause_button = wx.Button(self.panel_bottom, label="Pause")
        self.pause_button.SetBackgroundColour((0,150,150))
        self.prepare_button = wx.Button(self.panel_bottom, label="Prepare Session")
        self.puffc_but = wx.Button(self.panel_bottom, label='PuffCheck')
        self.tcpip_button = wx.Button(self.panel_bottom, label="TCPIP")
        self.mp285_button = wx.Button(self.panel_bottom, label="MP285")
        self.resetcam_button = wx.Button(self.panel_bottom, label="Reset Cam")
        self.resetlact_button = wx.Button(self.panel_bottom, label="Reset LAct")
        self.panel_bottom_sizer.AddStretchSpacer()
        self.panel_bottom_sizer.Add(self.prepare_button, flag=wx.EXPAND|wx.ALL, proportion=1)
        self.panel_bottom_sizer.AddStretchSpacer()
        self.panel_bottom_sizer.Add(self.start_button, flag=wx.EXPAND|wx.ALL, proportion=1)
        self.panel_bottom_sizer.AddStretchSpacer()
        self.panel_bottom_sizer.Add(self.pause_button, flag=wx.EXPAND|wx.ALL, proportion=1)
        self.panel_bottom_sizer.AddStretchSpacer()
        self.panel_bottom_sizer.Add(self.tcpip_button, flag=wx.EXPAND|wx.ALL, proportion=1)
        self.panel_bottom_sizer.AddStretchSpacer()
        self.panel_bottom_sizer.Add(self.mp285_button, flag=wx.EXPAND|wx.ALL, proportion=1)
        self.panel_bottom_sizer.AddStretchSpacer()
        self.panel_bottom_sizer.Add(self.resetcam_button, flag=wx.EXPAND|wx.ALL, proportion=1)
        self.panel_bottom_sizer.AddStretchSpacer()
        self.panel_bottom_sizer.Add(self.resetlact_button, flag=wx.EXPAND|wx.ALL, proportion=1)
        self.panel_bottom_sizer.AddStretchSpacer()
        self.panel_bottom_sizer.Add(self.puffc_but, proportion=1)
        self.panel_bottom_sizer.AddStretchSpacer()
        self.panel_bottom.SetSizerAndFit(self.panel_bottom_sizer)

        # main figure setup
        self.panel_fig = wx.Panel(self,3)
        self.panel_fig_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.fig = Figure( figsize=(8, 4) )
        self.gspec = gridspec.GridSpec(4,4,top=0.95,bottom=0.05,left=0.05,right=0.95,hspace=0.2,wspace=0.5)
        self.canvas = FigureCanvasWxAgg(self.panel_fig, -1, self.fig)
        self.panel_fig_sizer.Add(self.canvas, flag=wx.EXPAND|wx.ALL, proportion=1)
        self.panel_fig.SetSizerAndFit(self.panel_fig_sizer)
        
        # performance plot panel
        self.ax0 = self.fig.add_subplot(self.gspec[0:2,0:2])
        self.perfl,self.perfr,self.perfv,self.perfv_l,self.perfv_r,self.perf_data,self.w_perf_data,self.w_perfl,self.w_perfr,self.w_perfv,self.w_perfvl,self.w_perfvr = self.ax0.plot(np.zeros([self.n_perf_show,12])-1, color='gray')
        self.perfl.set_color('blue')
        self.perfr.set_color('green')
        self.w_perfl.set_color('blue')
        self.w_perfr.set_color('green')
        self.w_perfl.set_linewidth(3)
        self.w_perfr.set_linewidth(3)
        self.w_perf_data.set_linewidth(3)
        self.perfv.set_color('black')
        self.perfv.set_linestyle('dotted')
        self.perfv_l.set_color('blue')
        self.perfv_l.set_linestyle('dotted')
        self.perfv_r.set_color('green')
        self.perfv_r.set_linestyle('dotted')
        self.w_perfv.set_color('black')
        self.w_perfv.set_linestyle('dotted')
        self.w_perfv.set_linewidth(4)
        self.w_perfvl.set_color('blue')
        self.w_perfvl.set_linestyle('dotted')
        self.w_perfvl.set_linewidth(4)
        self.w_perfvr.set_color('green')
        self.w_perfvr.set_linestyle('dotted')
        self.w_perfvr.set_linewidth(4)
        self.perfl.set_alpha(0.4)
        self.perfr.set_alpha(0.4)
        self.perfv.set_alpha(0.4)
        self.w_perfl.set_alpha(0.4)
        self.w_perfr.set_alpha(0.4)
        self.w_perfv.set_alpha(0.4)
        self.perf_marks = [self.ax0.plot(m, -1)[0] for m in xrange(self.n_perf_show)]
        self.ax0.set_yticks(np.arange(0,1.1,0.05))
        self.ax0.yaxis.tick_right()
        self.ax0.set_ylim([-0.02,1.08])
        self.ax0.grid('on')
        self.ax0.set_xlim([-0.2,self.n_perf_show-0.8])
        
        # lick meter panel
        self.ax_lick = self.fig.add_subplot(self.gspec[2:,0:2])
        
        # movie panel
        self.ax_mov1 = self.fig.add_subplot(self.gspec[0:2,2:3])
        self.ax_mov2 = self.fig.add_subplot(self.gspec[0:2,3:])
        self.ax_mov1.axis('off')
        self.ax_mov2.axis('off')
        self.movd1 = self.ax_mov1.imshow(np.zeros([240,320]), cmap=cm.Greys_r, vmin=0, vmax=255)
        self.movd2 = self.ax_mov2.imshow(np.zeros([240,320]), cmap=cm.Greys_r, vmin=0, vmax=255)
        self.movdata = [self.movd1,self.movd2]
        
        # trial display panel
        self.ax_trial = self.fig.add_subplot(self.gspec[2:,2:])

        # live stream textbox
        self.std_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.stdout_box = wx.TextCtrl(self, wx.ID_ANY, style=wx.TE_MULTILINE|wx.TE_READONLY|wx.HSCROLL|wx.VSCROLL, size=(-1,100))
        self.stderr_box = wx.TextCtrl(self, wx.ID_ANY, style=wx.TE_MULTILINE|wx.TE_READONLY|wx.HSCROLL|wx.VSCROLL, size=(-1,100))
        self.usrinput_box = wx.TextCtrl(self, wx.ID_ANY, style=wx.TE_PROCESS_ENTER|wx.HSCROLL|wx.VSCROLL, size=(-1,100), value='(notes)')
        self.redir_out=RedirectText(self.stdout_box)
        self.redir_err=RedirectText(self.stderr_box)
        self.stderr_box.SetForegroundColour(wx.RED)
        self.std_sizer.Add(self.stdout_box, wx.ID_ANY, wx.ALL|wx.EXPAND)
        self.std_sizer.Add(self.stderr_box, wx.ID_ANY, wx.ALL|wx.EXPAND)
        self.std_sizer.Add(self.usrinput_box, wx.ID_ANY, wx.ALL|wx.EXPAND)

        # main view sizers
        self.sizer_global = wx.BoxSizer(wx.VERTICAL)
        self.sizer_main = wx.BoxSizer(wx.HORIZONTAL)
        self.sizer_v = wx.BoxSizer(wx.VERTICAL)

        self.sizer_v.Add(self.panel_top, flag=wx.EXPAND|wx.ALL, proportion=1)
        self.sizer_v.Add(self.panel_top2, flag=wx.EXPAND|wx.ALL, proportion=1)
        self.sizer_v.Add(self.panel_bottom, flag=wx.EXPAND|wx.ALL, proportion=1)
        self.sizer_v.Add(self.panel_fig, flag=wx.EXPAND|wx.ALL, proportion=100)

        self.sizer_main.Add(self.panel_left_sizer, flag=wx.EXPAND|wx.ALL, proportion=1)
        self.sizer_main.Add(self.sizer_v, flag=wx.EXPAND|wx.ALL, proportion=1)

        self.sizer_global.Add(self.std_sizer, flag=wx.EXPAND, proportion=1)
        self.sizer_global.Add(self.sizer_main, flag=wx.EXPAND, proportion=1)

        self.SetSizer(self.sizer_global)

        self.Show()
        self.Layout()
    def update_sub_choices(self, rewards={}):
        self.sub_names = sorted(self.sub_names)
        self.sub_box.Clear()
        self.sub_strs = ['{} ({:0.0f}uL due)'.format(s,1000.-rewards.get(s,0)) for s in self.sub_names]
        if self.sub_strs:
            self.sub_box.InsertItems(items=self.sub_strs, pos=0)
    def add_sub(self, s, rewards={}):
        if not isinstance(s, list):
            s = [s]
        s = [str(i) for i in s]
        self.sub_names += s
        self.sub_names = sorted(self.sub_names)
        self.update_sub_choices(rewards=rewards)
    def setup_axlick(self):
        self.ax_lick.clear()
        self.lick_data1,self.lick_data2,self.wheel_data = self.ax_lick.plot(np.zeros((self.n_lick_show,3)), alpha=0.5)
        self.ax_lick.set_ylim([-.9,10.1])
        self.ax_lick.set_xlim([0,self.n_lick_show])
    def set_bias(self, b):
        self.bias_widg.SetValue('{:0.2f} : {:0.2f}'.format(*b[::-1]))
    def set_manip(self, m):
        self.manip_widg.SetValue('{}'.format(m))
    def set_history(self, th):
        history,winhist = th.history_glob,th.history_win
        
        data = history['perc']
        windata = winhist['perc']
        markers = history['outcome']
        cors = history['side']
        perfl = history['perc_l']
        perfr = history['perc_r']
        winpl = winhist['perc_l']
        winpr = winhist['perc_r']
        perfv = history['valid']
        vall = history['valid_l']
        valr = history['valid_r']
        winval = winhist['valid']
        winvall = winhist['valid_l']
        winvalr = winhist['valid_r']

        shapes = np.array(['v','^','>','<','o','x',None])
        sizes = np.array([7,7,4,4,4,4,4])
        cor_cols = ['blue','green']
        i0 = 0
        if len(data) < self.n_perf_show:
            def pad(d):
                d = np.pad(d, (0,self.n_perf_show-len(d)), mode='constant', constant_values=-1)
                d[d==-1] = np.nan
                return d
            data,perfl,perfr,perfv,winpl,winpr,vall,valr,winval,windata,winvall,winvalr = map(pad,[data,perfl,perfr,perfv,winpl,winpr,vall,valr,winval,windata,winvall,winvalr])
            markers = np.pad(markers, (0,self.n_perf_show-len(markers)), mode='constant', constant_values=-1)
            cors = (np.pad(cors, (0,self.n_perf_show-len(cors)), mode='constant', constant_values=-1)).astype(int)
        elif len(data) >= self.n_perf_show:
            i0 = len(data) - self.n_perf_show
            def cut(d):
                d = d.iloc[-self.n_perf_show:]
                return d
            data,perfl,perfr,perfv,winpl,winpr,vall,valr,winval,windata,winvall,winvalr = map(cut,[data,perfl,perfr,perfv,winpl,winpr,vall,valr,winval,windata,winvall,winvalr])
            markers = markers.iloc[-self.n_perf_show:].astype(int)
            cors = cors.iloc[-self.n_perf_show:].astype(int)
        
        with self.fig_lock:
            self.perf_data.set_ydata(data)
            self.perfl.set_ydata(perfl)
            self.perfr.set_ydata(perfr)
            self.perfv.set_ydata(perfv)
            self.perfv_l.set_ydata(vall)
            self.perfv_r.set_ydata(valr)
            
            self.w_perf_data.set_ydata(windata)
            self.w_perfl.set_ydata(winpl)
            self.w_perfr.set_ydata(winpr)
            self.w_perfv.set_ydata(winval)
            self.w_perfvl.set_ydata(winvall)
            self.w_perfvr.set_ydata(winvalr)
            for i,d,new_m,mline,cor in zip(range(len(data)), data, markers, self.perf_marks, cors):
                new_m = int(new_m)
                cor = int(cor)
                mline.set_marker(shapes[new_m])
                mline.set_markersize(sizes[new_m])
                mline.set_markeredgewidth(1)
                mline.set_markeredgecolor(cor_cols[cor])
                mline.set_markerfacecolor(cor_cols[cor])
                mline.set_ydata(d)
            self.ax0.set_xticklabels([str(int(i0+float(i))) for i in self.ax0.get_xticks()])
            try:
                self.fig.canvas.draw()
            except:
                pass
    def set_cam(self, data):
        if data is None:
            return
        with self.fig_lock:
            for fr,imd in zip(data,self.movdata):
                imd.set_data(fr)
            self.fig.canvas.draw()
    def set_lick_data(self, data):
        with self.fig_lock:
            for d,line in zip(data,[self.lick_data1,self.lick_data2,self.wheel_data]):
                line.set_ydata(d[-self.n_lick_show:])
            self.fig.canvas.draw()
    def set_trial_data(self, th, sesh):
        times = th.trt['time']
        sides = th.trt['side']
        times_l,times_r = times[sides==0],times[sides==1]
        corside = th.trial.side

        with self.fig_lock:
            self.ax_trial.cla()
            corcols = {0:'blue',1:'green'}

            self.ax_trial.plot(np.ones(times_r.shape), times_r, marker='o', markeredgecolor='none', markerfacecolor='green', linestyle='None')
            self.ax_trial.plot(np.zeros(times_l.shape), times_l, marker='o', markeredgecolor='none', markerfacecolor='blue', linestyle='None')
            
            self.ax_trial.hlines(0, -1., 2.,colors='k',linestyles='dashed')
            self.ax_trial.hlines(th.stim_phase_pad[0], -1., 2.,colors='k',linestyles='dashed')
            self.ax_trial.hlines(th.stim_phase_pad[0]+th.trial.dur, -1., 2.,colors=corcols[corside],linestyles='dashed')
            self.ax_trial.hlines(sum(th.stim_phase_pad)+th.trial.dur, -1., 2.,colors='gray',linestyles='dashed')
            self.ax_trial.hlines(sum(th.stim_phase_pad)+th.trial.dur+th.trial.delay, -1., 2.,colors='k',linestyles='dashed')
            
            ylim = th.phase_dur+th.trial.delay+0.4
            
            self.ax_trial.set_ylim([-0.2,ylim])
            self.ax_trial.set_xlim([-1.,2.])
            self.ax_trial.set_xticks([],[])
            self.fig.canvas.draw()

class MoviePanel(wx.Panel):
    def __init__(self, parent, size=(320,240)):
        wx.Panel.__init__(self, parent, wx.ID_ANY, (0,0), size)
        self.size = size
        height, width = size[::-1] 
        self.dummy = np.empty((height,width,3), dtype=np.uint8)
        self.SetSize((width, height))

        self.bmp = wx.BitmapFromBuffer(width, height, self.dummy)

        self.Bind(wx.EVT_PAINT, self.on_paint)

    def on_paint(self, evt):
        dc = wx.BufferedPaintDC(self)
        dc.DrawBitmap(self.bmp, 0, 0)

    def set_frame(self, fr):
        if fr is None:
            return
        fr = np.array([fr,fr,fr]).transpose([1,2,0]).astype(np.uint8)
        self.dummy.flat[:] = fr.flat[:]
        self.bmp.CopyFromBuffer(self.dummy)
        self.Refresh()


class MP285View(wx.Frame):
    def __init__(self, parent):
        wx.Frame.__init__(self, parent, title="MP285 Control")
        self.Center()
        self.sizer = wx.GridSizer(rows=15, cols=3)

        self.but_set_home = wx.Button(self, label='Set Home')
        self.but_set_stim = wx.Button(self, label='Set Stim Position')
        self.but_set_lick = wx.Button(self, label='Set Lick Position')
        self.but_goto_home = wx.Button(self, label='Go Home')
        self.but_goto_stim = wx.Button(self, label='Goto Stim Position')
        self.but_goto_lick = wx.Button(self, label='Goto Lick Position')
        self.gap1 = wx.Button(self, label='')
        self.gap2 = wx.Button(self, label='')
        self.gap3 = wx.Button(self, label='')

        self.sizer.Add(self.but_set_home, flag=wx.ALL|wx.EXPAND, proportion=1)
        self.sizer.Add(self.but_set_stim, flag=wx.ALL|wx.EXPAND, proportion=1)
        self.sizer.Add(self.but_set_lick, flag=wx.ALL|wx.EXPAND, proportion=1)
        self.sizer.Add(self.gap1, flag=wx.ALL|wx.EXPAND, proportion=1)
        self.sizer.Add(self.gap2, flag=wx.ALL|wx.EXPAND, proportion=1)
        self.sizer.Add(self.gap3, flag=wx.ALL|wx.EXPAND, proportion=1)
        self.sizer.Add(self.but_goto_home, flag=wx.ALL|wx.EXPAND, proportion=1)
        self.sizer.Add(self.but_goto_stim, flag=wx.ALL|wx.EXPAND, proportion=1)
        self.sizer.Add(self.but_goto_lick, flag=wx.ALL|wx.EXPAND, proportion=1)

        self.ctrl_buttons = {}
        UP,DOWN = u'\u2191',u'\u2193'
        dirdic = dict(up=UP,down=DOWN)
        for direc in ['up','down']:
            self.ctrl_buttons[direc] = {}
            mags = [1000,500,100]
            if direc=='down':
                mags = mags[::-1]
            for mag in mags:
                self.ctrl_buttons[direc][mag] = {}
                for ax in ['x','y','z']:
                    lab = u'{} {} {}'.format(ax.upper(), dirdic[direc], mag)
                    self.ctrl_buttons[direc][mag][ax] = wx.Button(self, label=lab)
                    self.sizer.Add(self.ctrl_buttons[direc][mag][ax], proportion=1, flag=wx.EXPAND|wx.ALL)

        # main view sizers
        self.SetSizer(self.sizer)
        self.Layout()


