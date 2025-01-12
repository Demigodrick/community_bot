import datetime
import sys

log_file_path = 'resources/zippy.log'


def check_last_log_timestamp(log_file):
    now = datetime.datetime.utcnow()
    time_format = "%Y-%m-%d %H:%M:%S,%f"

    try:
        with open(log_file, 'r') as file:
            lines = file.readlines()
            if not lines:
                print("Log file is empty.")
                return False

            last_line = lines[-1]
            timestamp_str = last_line.split(' - ')[0].strip()
            last_log_time = datetime.datetime.strptime(
                timestamp_str, time_format)

            # print(f"Last log time: {last_log_time}")
            # print(f"Current time: {now}")
            # print(f"Time difference (seconds): {(now - last_log_time).total_seconds()}")

            if (now - last_log_time).total_seconds() < 60:
                return True
    except Exception as e:
        print(f"Error reading log file: {e}")
        return False

    return False


if __name__ == "__main__":
    if check_last_log_timestamp(log_file_path):
        sys.exit(0)
    else:
        sys.exit(1)
