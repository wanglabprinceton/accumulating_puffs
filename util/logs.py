import logging, sys

def setup_logging(outwin=None,errwin=None):
    logger = logging.getLogger()
    logger.setLevel(logging.NOTSET)

    handler_file = logging.FileHandler('run.log')
    if outwin:
        handler_disp = logging.StreamHandler(outwin)
    if errwin:
        handler_err = logging.StreamHandler(errwin)

    formatter = logging.Formatter('%(asctime)s : %(message)s', datefmt='%Y.%m.%d-%H.%M.%S')
    handler_file.setFormatter(formatter)
    if outwin:
        handler_disp.setFormatter(formatter)
    if errwin:
        handler_err.setFormatter(formatter)
        handler_err.setLevel(logging.WARNING)

    logger.addHandler(handler_file)
    if outwin:
        logger.addHandler(handler_disp)
    if errwin:
        logger.addHandler(handler_err)

    logging.info('Logging setup, beginning run.')
