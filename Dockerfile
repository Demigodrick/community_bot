# Use an official Python runtime as a parent image
FROM python:3-slim

# Set the working directory in the container to /bot
WORKDIR /bot

# Create a virtual environment and activate it
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy the current directory contents into the container at /bot
COPY requirements.txt .
COPY bot_query.py .
COPY config.py .
COPY main.py .
COPY .env .
COPY resources/ ./resources/
COPY pythorhead ./pythorhead

# Install any needed packages specified in requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# Run main.py when the container launches
CMD ["python3", "main.py"]
