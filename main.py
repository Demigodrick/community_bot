from bot_query import check_pms, login, check_db
import schedule
import time
import logging

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

logging.info("Hello! Bot starting...")

if __name__ == "__main__":
    login()
    check_db()
    schedule.every(3).seconds.do(check_pms)


while True:
    schedule.run_pending()
    time.sleep(1)

