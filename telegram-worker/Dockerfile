FROM python:3.12-slim

WORKDIR /app

COPY telegram-worker/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY telegram-worker/worker.py ./worker.py

CMD ["python", "worker.py"]
