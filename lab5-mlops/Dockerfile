FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements-service.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements-service.txt
FROM python:3.12-slim AS runtime
ARG MODEL_DIR=models
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY --from=builder /install /usr/local
COPY src ./src
COPY service ./service
COPY ${MODEL_DIR} ./models
RUN useradd --create-home --uid 10001 appuser
USER appuser
EXPOSE 8000
CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8000"]
