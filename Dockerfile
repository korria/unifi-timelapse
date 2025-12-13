FROM python:3.9-slim

# Install system dependencies (FFmpeg and curl for healthcheck)
RUN apt-get update && \
    apt-get install -y ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
RUN pip install requests schedule

# Copy the script
COPY main.py .

# Run the script
CMD ["python", "-u", "main.py"]
