from bot_query import check_pms, login, check_dbs, get_new_users, get_communities, humblebundle, game_deals, steam_deals, check_comments, check_posts, game_news, check_reports
from config import settings
import logging
import schedule
import time
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

logging.info("Hello! Bot starting...")
logging.info("Bot Version 0.3.4")

if __name__ == "__main__":
    
    #run once
    login()
    check_dbs()

    #seconds
    schedule.every(5).seconds.do(check_pms)
    schedule.every(10).seconds.do(get_new_users)
    schedule.every(30).seconds.do(get_communities)
    schedule.every(30).seconds.do(check_reports)
      

    #minutes
    schedule.every(30).minutes.do(humblebundle)
    schedule.every(10).minutes.do(game_deals)
    schedule.every(10).minutes.do(steam_deals)
    schedule.every(10).minutes.do(game_news)

    #optional 
    if settings.SLUR_ENABLED == True:
        schedule.every(5).seconds.do(check_comments)
        schedule.every(5).seconds.do(check_posts)

while True:
     schedule.run_pending()
     time.sleep(1)
