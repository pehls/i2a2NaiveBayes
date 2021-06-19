import logging
import datetime

from src.directory_utilities import validate_or_make_directory

date = "{:%Y-%m-%d}".format(datetime.datetime.now())
log_file_string = "./logs/{}.log".format(date)

validate_or_make_directory(log_file_string)

logFormatter = logging.Formatter("%(asctime)s - [%(levelname)s]  %(message)s")
logger = logging.getLogger()

fileHandler = logging.FileHandler(log_file_string)
fileHandler.setFormatter(logFormatter)
logger.addHandler(fileHandler)

consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)
logger.addHandler(consoleHandler)