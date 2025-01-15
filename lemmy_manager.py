from pythorhead import Lemmy
from config import settings

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
