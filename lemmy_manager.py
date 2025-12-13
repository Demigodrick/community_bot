from pythorhead import Lemmy
from config import settings
import sys
import time
import logging

# Global variable
LEMMY = None

def login():
    global LEMMY
    
    try:
        LEMMY = Lemmy("https://" + settings.INSTANCE, request_timeout=10)
        LEMMY.log_in(settings.USERNAME, settings.PASSWORD)
        logging.info("Successfully logged in to Lemmy instance")
        return LEMMY
    except Exception as e:
        logging.error(f"Failed to login to Lemmy: {e}")
        raise

def get_lemmy_instance():
    global LEMMY
    try:
        if LEMMY is None:
            login()
        return LEMMY
    except Exception as e:
        logging.error(f"Failed to get Lemmy instance: {e}")
        raise

def restart_bot():
    logging.info("Bot restart requested, shutting down in 15 seconds...")
    time.sleep(15) 
    sys.exit(1)
