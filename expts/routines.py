from util import now,now2

def add_to_saver_buffer(buf, source, data, ts=None, ts2=None, columns=None):
    if ts is None:
        ts = now()
    if ts2 is None:
        ts2 = now2()
    buf.put([source, data, ts, ts2, columns])