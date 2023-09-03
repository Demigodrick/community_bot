from bot_query import check_pms, login, check_dbs, get_new_users, get_communities, humblebundle, game_deals
import schedule
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

logging.info("Hello! Bot starting...")

if __name__ == "__main__":
    login()
    check_dbs()
    schedule.every(5).minutes.do(humblebundle)
    schedule.every(5).minutes.do(game_deals)
    schedule.every(5).seconds.do(check_pms)
    schedule.every(5).seconds.do(get_new_users)
    schedule.every(30).seconds.do(get_communities)  


while True:
    schedule.run_pending()
    time.sleep(1)

