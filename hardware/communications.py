import config, logging

if config.TESTING_MODE:
    from dummy import DAQIn, DAQOut, Trigger, SICommunicator

elif not config.TESTING_MODE:
    try:
        from ni845x import NI845x
    except:
        NI845x = None

    class SICommunicator():
        def __init__(self, on=True):
            self.on = on
            if not self.on:
                return

            self.ni = NI845x()

        def start_acq(self):
            if self.on:
                self.ni.write_dio(config.ni845x_lines['start_acq'], 1)
                self.ni.write_dio(config.ni845x_lines['start_acq'], 0)
        
        def stop_acq(self):
            if self.on:
                self.ni.write_dio(config.ni845x_lines['stop_acq'], 1)
                self.ni.write_dio(config.ni845x_lines['stop_acq'], 0)

        def i2c(self, msg):
            if not self.on:
                return

            try:
                self.ni.write_i2c(msg)
            except:
                logging.error('I2C communication failed!')

        def end(self):
            if self.on:
                self.ni.end()
