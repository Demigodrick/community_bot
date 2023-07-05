from bot_query import check_pms, login
import schedule
import time
import logging

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

logging.info("Bot starting...")

if __name__ == "__main__":
    login()
    schedule.every(3).seconds.do(check_pms)


while True:
    schedule.run_pending()
    time.sleep(1)

