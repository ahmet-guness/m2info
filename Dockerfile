FROM python:3.12-alpine

# Set timezone and environment flags
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Europe/Istanbul

# Install tzdata and ca-certificates for HTTPS & accurate Turkish timezone
RUN apk add --no-cache tzdata ca-certificates sqlite

WORKDIR /app

# Copy all python source files
COPY *.py ./

# Create data directory for persistent SQLite database and state
RUN mkdir -p /app/data

# Run bot in daemon mode
CMD ["python", "bot.py"]
