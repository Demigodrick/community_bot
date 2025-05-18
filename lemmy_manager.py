from pythorhead import Lemmy
from config import settings
import sys
import time

# Global variable
LEMMY = None

def login():
    global LEMMY
     
    LEMMY = Lemmy("https://" + settings.INSTANCE, request_timeout=10)
    LEMMY.log_in(settings.USERNAME, settings.PASSWORD)
    return LEMMY

def get_lemmy_instance():
    global LEMMY
    if LEMMY is None:
        login()
    return LEMMY

def restart_bot():
    time.sleep(15) 
    sys.exit(1)  