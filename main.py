from bot_query import check_pms, login, check_dbs, get_new_users, get_communities
import schedule
import time
import logging

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

logging.info("Hello! Bot starting...")

if __name__ == "__main__":
    login()
    check_dbs()
    schedule.every(3).seconds.do(check_pms)
    schedule.every(3).seconds.do(get_new_users)
    schedule.every(20).seconds.do(get_communities)  

while True:
    schedule.run_pending()
    time.sleep(1)

