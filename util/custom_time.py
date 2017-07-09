import time

def now():
    return time.clock() #Platform-dependent, on windows has high precision. no correspondence to "real" time of day
    #return time.time() # Platform-invariant, but low resolution on windows
def now2():
    return time.time()
