import socket, time
import numpy as np
import logging, json

class TCPIP():
    def __init__(self, tcpip_address, tcpip_port=6666, tcpip_terminator='\n'):
    
        if tcpip_address is None:
            self._valid = False
            return

        self._valid = True
        self.tcpip_address = tcpip_address
        self.tcpip_port = tcpip_port
        self.tcpip_terminator = tcpip_terminator

        # setup socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
        self.socket.settimeout(0.500) #brief when initiating
        try:
            self.socket.connect((self.tcpip_address, self.tcpip_port))
        except socket.timeout:
            pass
            #logging.warning('Socket not connected.')    
        except:
            logging.warning('TCPIP not connected; turn on internet to send messages.')
            return
        self.socket.settimeout(10.0)

    def send(self, msg):
        if not self._valid:
            return True
        try:
            # msg : a JSON-formatted string or dict to be converted to one
            if isinstance(msg, dict):
                msg = json.dumps(msg)
            self.socket.send(msg.encode(encoding='utf-8'))
            self.socket.send(self.tcpip_terminator.encode(encoding='utf-8'))
        except socket.timeout:
            logging.warning('TCPIP message did not send.')
            return False
          
        try:
            r = self.socket.recv(3)
            if r.decode('UTF8') != '_ok':
                logging.warning('TCPIP did not receive OK response; communication issue.')
                return False
            else:
                self._reconnect()
        except socket.timeout:
            logging.warning('Attempted TCPIP send; no reply from remote; re-establish connection.')
            return False
        
        return True

    def end(self):
        if self._valid:
            self.socket.close()

    def reconnect(self):
        if not self._valid:
            return True
        return self._reconnect()
    def _reconnect(self):
        #print ('Click reconnect on remote computer...')
        self.socket.close()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(10.0)
        try:
            self.socket.connect((self.tcpip_address, self.tcpip_port))
        except socket.timeout:
            logging.warning('Reconnect failed; socket not connected.')    
            return False
        return True

        #print('Reconnected.')

if __name__ == '__main__':
    address = '128.112.217.150'
    t = TCPIP(address)
