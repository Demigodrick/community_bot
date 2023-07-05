from bot_query import check_pms
import schedule
import time

schedule.every(3).seconds.do(check_pms)

while True:
    schedule.run_pending()
    time.sleep(1)

