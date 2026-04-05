FROM python:3.13-slim-bookworm

# OpenCV runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libv4l-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create directories for runtime data
RUN mkdir -p /app/logs /app/queue /app/config

EXPOSE 5000

# Default: run the circle detector web app
CMD ["python3", "-m", "circle_detector.app"]
