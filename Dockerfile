FROM python:3
RUN python3 -m venv /opt/venv
COPY requirements.txt .
COPY bot_query.py .
COPY config.py .
COPY main.py .
COPY .env .
COPY pythorhead ./pythorhead
RUN . opt/venv/bin/activate && pip install -r requirements.txt
CMD . /opt/venv/bin/activate && exec python3 main.py
