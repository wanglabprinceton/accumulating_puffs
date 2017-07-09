# manipulations refers to any perturbation condition that is specified for this particular behavioural training session, and is intended to be implemented by the software
# for example: optogenetic stimulation, imaging patterns, etc.
# a manipulation is either a single manip constant, or a list thereof with probabilities

## manipulation values constants
MANIP_NONE                  = 0
#opto
MANIP_OPTO_STIMDELAY        = 1 # stim, delay phases
MANIP_OPTO_LICK             = 2 # lick phase
MANIP_OPTO_REWARDITI        = 3 # reward and iti phases
# convenience strings strictly for display:
manip_strs = {   0 : 'none',
                 1 : 'stim/delay',
                 2 : 'lick',
                 3 : 'reward/iti',
                }

manipulations = {       'none'          : MANIP_NONE,
                        'opto_stim_lick_rew' : [ [MANIP_NONE, MANIP_OPTO_STIMDELAY, MANIP_OPTO_LICK, MANIP_OPTO_REWARDITI] , [0.85, 0.06, 0.03, 0.06] ],
                        'opto_stim' : [[MANIP_NONE, MANIP_OPTO_STIMDELAY], [0.88, 0.12]],
                      }

default_manipulation = manipulations['none']

