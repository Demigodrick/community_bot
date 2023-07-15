from bot_query import check_pms, login, check_vote_db, get_new_users, check_user_db
import schedule
import time
import logging

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

logging.info("Hello! Bot starting...")

if __name__ == "__main__":
    login()
    check_vote_db()
    check_user_db()
    schedule.every(3).seconds.do(check_pms)
    schedule.every(3).seconds.do(get_new_users)

while True:
    schedule.run_pending()
    time.sleep(1)

