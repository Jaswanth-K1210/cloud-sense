# Build from the repo root: docker build -f backend/Dockerfile .
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend backend
COPY eval eval
ENV DATABASE_URL=sqlite:////data/cloudsense.db
EXPOSE 8000
CMD ["sh", "-c", "python -m backend.store.seed_demo && uvicorn backend.app:app --host 0.0.0.0 --port 8000"]
