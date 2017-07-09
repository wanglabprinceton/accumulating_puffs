try:
	import winsound
except:
	winsound = None
import threading

ERROR,POP,LASER,INTRO,BUZZ = 0,1,2,3,4
def sounds(s):
   return 'media/'+str(s)+'.wav'

class Speaker(object):
    def __init__(self, saver=None):
        self.playing = []
        self.saver = saver
        self.event = threading.Event()
    def _play(self, filename, wait):
        while self.event.is_set():
            pass
            if wait==False:
                return
        self.event.set()

        if self.saver:
            self.saver.write('speaker', dict(filename=filename))

        if winsound != None:
            winsound.PlaySound(sounds(filename), winsound.SND_FILENAME)

        self.event.clear()
    def error(self, wait=True):
        threading.Thread(target=self._play, args=(ERROR,wait)).start()
    def pop(self, wait=True):
        threading.Thread(target=self._play, args=(POP,wait)).start()
    def laser(self, wait=True):
        threading.Thread(target=self._play, args=(LASER,wait)).start()
    def intro(self, wait=True):
        threading.Thread(target=self._play, args=(INTRO,wait)).start()
    def wrong(self, wait=True):
        threading.Thread(target=self._play, args=(BUZZ,wait)).start()
