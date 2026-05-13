FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p data/music

ENV PORT=8090
EXPOSE ${PORT}

CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 run:app
