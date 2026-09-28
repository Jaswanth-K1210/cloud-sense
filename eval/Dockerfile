FROM python:3.11-slim
# Build from the repo root: docker build -f eval/Dockerfile .

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 7860

CMD ["uvicorn", "eval.cloudsense_env.server.app:app", "--host", "0.0.0.0", "--port", "7860"]
