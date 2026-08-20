FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY slate_app slate_app
COPY app app
COPY grafana grafana
CMD ["sh", "-c", "uvicorn slate_app.main:app --host 0.0.0.0 --port ${PORT}"]
