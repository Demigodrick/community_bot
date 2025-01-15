from pythorhead import Lemmy
from config import settings

# Global variable
lemmy = None

def login():
    global lemmy
    lemmy = Lemmy("https://" + settings.INSTANCE, request_timeout=10)
    lemmy.log_in(settings.USERNAME, settings.PASSWORD)
    return lemmy

def get_lemmy_instance():
    global lemmy
    if lemmy is None:
        login()
    return lemmy
