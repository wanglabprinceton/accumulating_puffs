"""
This file is used to run the experiment.
Note that it should always be run from within the main project directory, since the structure of the package is designed with that expectation.
"""
if __name__ == '__main__':
    from expts.controllers import Controller
    Controller()
    #import profile
    #profile.run('Controller()')
