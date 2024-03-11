# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container to /bot
WORKDIR /bot

# Install system dependencies required for Rust
#RUN apt-get update && apt-get install -y curl gcc libssl-dev pkg-config && \
#    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

# Add Cargo to PATH
ENV PATH="/root/.cargo/bin:$PATH"

# Create a virtual environment and activate it
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN python3 -m pip install --upgrade pip

# Copy the current directory contents into the container at /bot
COPY requirements.txt .
COPY bot_query.py .
COPY healthcheck.py .
COPY bot_strings.py .
COPY config.py .
COPY main.py .
COPY .env .
COPY resources/ ./resources/

# Install any needed packages specified in requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

HEALTHCHECK --interval=1m --timeout=10s \
  CMD python ./healthcheck.py || exit 1

# Run main.py when the container launches
CMD ["python3", "main.py"]
