FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1
ENV PORT=8003

EXPOSE 8000 8003

# Run both Discord bot and scraper
CMD ["python", "luxury_sniper.py"]
