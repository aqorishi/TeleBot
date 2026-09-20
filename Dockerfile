FROM python:3.12-slim

# Prevent Python from writing .pyc files
# and make logs appear immediately
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Start the bot
CMD ["python", "bot.py"]