import os
import logging
from logging.handlers import RotatingFileHandler

BASE_DIR = os.path.dirname(os.path.dirname(__file__))  # one level above src/
log_file = os.path.join(BASE_DIR, "logs", "application.csv")

# Ensure that the directory for the log file exists
log_dir = os.path.dirname(log_file)
os.makedirs(log_dir, exist_ok=True)

# Set up the RotatingFileHandler
handler = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=5)
formatter = logging.Formatter('%(asctime)s,%(levelname)s,%(filename)s,"%(message)s"')
handler.setFormatter(formatter)

# Create a logger instance and attach the handler
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(handler)