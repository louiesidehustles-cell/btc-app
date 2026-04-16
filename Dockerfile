FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir flask requests pytz

CMD ["python", "app.py"]
