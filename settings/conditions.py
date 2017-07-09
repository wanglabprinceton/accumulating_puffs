# conditions refers to anything about the subject that is true regardless of the behavior being run
# for example: species, viral/CNO/saline injections, fear conditioned, unique surgery, LED pointed at head, etc.

conditions = dict(  basic = 0,
                    musc = 1,
                    sal = 2,
                    )


"""
Meanings of conditions values
-----------------------------------
0 : no manipulation
1 : 0.2mL CNO, 20 minutes before session
2 : 0.2mL saline, 20 minutes before session
3 : optogenetics LED, aimed at Crus I on the left, w/ posterior masking LED under same control
4 : optogenetics LED, aimed at Crus I on the right, w/ posterior masking LED under same control
"""

default_condition = conditions['basic']
