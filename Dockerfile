# ---- 1. Build the React frontend ---------------------------------------------
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 2. Python API + analytics engine, serving the built frontend -------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    INSIGHTFLOW_DATA_DIR=/data
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY --from=web /web/dist frontend/dist
WORKDIR /app/backend
VOLUME ["/data"]
EXPOSE 8000
# DuckDB is an in-process engine: run a single worker process
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
