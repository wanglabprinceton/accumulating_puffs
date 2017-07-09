
# rule definitions for a level (ex. level 4 is rule_full)
RULE_FULL,RULE_PASSIVE,RULE_PHASE,RULE_FAULT,RULE_HINT = 0,1,2,3,4
# rule index that make up the above level rules (ex. hints are present)
RULEI_ANY, RULEI_SIDE, RULEI_PHASE, RULEI_FAULT, RULEI_HINTDELAY, RULEI_HINTREWARD = 0,1,2,3,4,5
rules = {    # [rule_any, rule_side, rule_phase, rule_fault, rule_hint_delay, rule_hint_reward, rule_stereo]
            RULE_FULL:          [True, True, True, False, False, False,],
            RULE_PASSIVE:       [False, False, False, True, True, False,],
            RULE_PHASE:         [True, True, True, True, False, False,],
            RULE_FAULT:         [True, True, True, True, True, False,],
            RULE_HINT:          [True, True, True, False, True, False,],
        }
