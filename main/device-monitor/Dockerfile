FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# HTTP API giám sát (cho web/app đọc trạng thái + gửi lệnh)
EXPOSE 8090

CMD ["python", "consumer.py"]
