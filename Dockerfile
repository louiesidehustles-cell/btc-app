<<<<<<< HEAD
FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir flask requests pytz

CMD ["python", "app.py"]
=======
FROM python:3.11

WORKDIR /app

COPY . .

RUN pip install -r requirements.txt

CMD ["python", "btc_alert.py"]
>>>>>>> 47b7d13 (add auto deploy)
