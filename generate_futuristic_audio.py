# docker-compose.yml
version: "3.8"

services:
  insta-jokes:
    build: .
    image: insta-jokes:latest
    container_name: insta-jokes
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./outputs:/app/outputs
      - ./assets:/app/assets
    ports:
      - "8080:8080"       # webhook port (optional)
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

---

# Dockerfile
FROM python:3.11-slim

LABEL maintainer="you@example.com"

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      ffmpeg \
      git \
      curl \
      ca-certificates \
      jq \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

COPY . /app
COPY ffprobe_debug.sh /usr/local/bin/ffprobe_debug.sh
RUN chmod +x /usr/local/bin/ffprobe_debug.sh

RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONUNBUFFERED=1

CMD ["python", "instagram_hourly_jokes.py"]

---

# requirements.txt
moviepy
numpy
Pillow
requests
python-dotenv
instagrapi
Flask

---

# .env.example
# Instagram credentials
IG_USERNAME=your_username
IG_PASSWORD=your_password

# Bot configuration
POST_INTERVAL_SECONDS=3600
ALLOW_AUTOPUBLISH=false
POST_VIDEO=true

# Fonts and assets
FONT_PATH=
AUDIO_FILE=assets/futuristic.wav
OUTPUT_DIR=outputs

# SMTP email alerts (optional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_app_password
ALERT_EMAIL_FROM=your_email@gmail.com
ALERT_EMAIL_TO=alert_destination@example.com

# Webhook alerts (optional)
WEBHOOK_ENABLED=false
WEBHOOK_PORT=8080
WEBHOOK_PATH=/insta-alert

---

# ffprobe_debug.sh
#!/usr/bin/env bash
# ffprobe_debug.sh <path-to-file>
# Writes /app/outputs/ffprobe_<basename>.json with ffprobe JSON output
set -euo pipefail
if [ $# -lt 1 ]; then
  echo "Usage: $0 <video-file>"
  exit 2
fi
IN="$1"
B="$(basename "$IN")"
OUT="/app/outputs/ffprobe_${B%.*}.json"
ffprobe -v quiet -print_format json -show_format -show_streams "$IN" > "$OUT" 2>&1 || echo "ffprobe exited non-zero, partial output saved to $OUT"
echo "Wrote $OUT"

---

# Makefile

.PHONY: build run logs stop clean

build:
	docker compose build

run:
	docker compose up -d

logs:
	docker compose logs -f insta-jokes

stop:
	docker compose down

clean:
	docker system prune -af --volumes
