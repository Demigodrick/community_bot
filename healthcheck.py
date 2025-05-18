import datetime
import sys
import os
import itertools

# Ref: https://stackoverflow.com/questions/2301789/how-to-read-a-file-in-reverse-order
def reverse_readline(filename, buf_size=8192):
    """A generator that returns the lines of a file in reverse order"""
    with open(filename, 'rb') as fh:
        segment = None
        offset = 0
        fh.seek(0, os.SEEK_END)
        file_size = remaining_size = fh.tell()
        while remaining_size > 0:
            offset = min(file_size, offset + buf_size)
            fh.seek(file_size - offset)
            buffer = fh.read(min(remaining_size, buf_size))
            # remove file's last "\n" if it exists, only for the first buffer
            if remaining_size == file_size and buffer[-1] == ord('\n'):
                buffer = buffer[:-1]
            remaining_size -= buf_size
            lines = buffer.split('\n'.encode())
            # append last chunk's segment to this chunk's last line
            if segment is not None:
                lines[-1] += segment
            segment = lines[0]
            lines = lines[1:]
            # yield lines in this chunk except the segment
            for line in reversed(lines):
                # only decode on a parsed line, to avoid utf-8 decode error
                yield line.decode()
        # Don't yield None if the file was empty
        if segment is not None:
            yield segment.decode()

LOG_FILE_PATH = 'resources/zippy.log'


def check_last_log_timestamp(log_file):
    now = datetime.datetime.now(datetime.UTC)
    time_format = "%Y-%m-%d %H:%M:%S,%f"

    try:
        for line in itertools.islice(reverse_readline(log_file), 250):
            if not line:
                print("Log file is empty.")
                return False

            timestamp_str = line.split(' - ')[0].strip()
            last_log_time = datetime.datetime.strptime(timestamp_str, time_format).astimezone(tz=datetime.UTC)

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
    if check_last_log_timestamp(LOG_FILE_PATH):
        sys.exit(0)
    else:
        sys.exit(1)
