import logging
import time
import schedule

from lemmy_manager import login
from config import settings

from bot_code import (
    check_pms, check_dbs, get_new_users, get_communities, steam_deals, 
    check_comments, check_posts, check_reports, check_scheduled_posts, 
    clear_notifications, RSS_feed, check_version
)

# Call login function
login()



logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s')

logging.info("Hello! Bot starting...")

if __name__ == "__main__":

    # run once
    check_version()
    check_dbs()

    # seconds
    schedule.every(5).seconds.do(check_pms)
    schedule.every(10).seconds.do(get_new_users)
    schedule.every(30).seconds.do(get_communities)
    schedule.every(30).seconds.do(check_reports)
    schedule.every(30).seconds.do(check_scheduled_posts)

    # minutes
    schedule.every(30).minutes.do(clear_notifications)
    schedule.every(10).minutes.do(steam_deals)

    # optional
    if settings.SLUR_ENABLED:
        schedule.every(10).seconds.do(check_comments)
        schedule.every(10).seconds.do(check_posts)
    if settings.RSS_ENABLED:
        schedule.every(10).minutes.do(RSS_feed)

while True:
    schedule.run_pending()
    time.sleep(1)
