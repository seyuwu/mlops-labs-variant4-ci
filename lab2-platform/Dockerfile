FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim AS runtime
ARG APP_VERSION=v1
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
ENV APP_VERSION=${APP_VERSION}
WORKDIR /app
COPY --from=builder /install /usr/local
COPY app ./app
RUN useradd --create-home --uid 10001 appuser
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
