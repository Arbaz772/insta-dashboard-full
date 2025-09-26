# Use official slim Python image
FROM python:3.11-slim


# Set working directory
WORKDIR /app


# Install system dependencies (ffmpeg for video, build tools for some pip packages)
RUN apt-get update \
&& apt-get install -y --no-install-recommends \
build-essential \
ffmpeg \
git \
libsndfile1 \
&& apt-get clean \
&& rm -rf /var/lib/apt/lists/*


# Copy application files
COPY . /app


# Install Python dependencies from requirements.txt
RUN pip install --no-cache-dir -r requirements.txt


# Ensure outputs directory exists
RUN mkdir -p /app/outputs


# Make Python output unbuffered (helpful for logs)
ENV PYTHONUNBUFFERED=1


# Default command
CMD ["python", "instagram_hourly_jokes_v_2.py"]