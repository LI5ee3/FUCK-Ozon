FROM python:3.14-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY static static
ENV DATA_DIR=/app/data PYTHONDONTWRITEBYTECODE=1
CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT}"]
