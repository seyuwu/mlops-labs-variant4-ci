from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
from uuid import UUID, uuid4
import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
import pika
import redis
from pydantic import BaseModel, Field
from src.common import FEATURES

MODEL_DIR = Path('models')


@asynccontextmanager
async def lifespan(app):
    app.state.model = joblib.load(MODEL_DIR / 'model.joblib')
    app.state.metadata = json.loads((MODEL_DIR / 'metadata.json').read_text(encoding='utf-8'))
    yield


app = FastAPI(title='Оценка риска отчисления', version='1.0.0', lifespan=lifespan)


class Features(BaseModel):
    attendance: float = Field(ge=0, le=1)
    completed_percent: float = Field(ge=0, le=100)
    weekly_hours: float = Field(ge=0, le=168)
    days_inactive: float = Field(ge=0, le=3650)
    prior_score: float = Field(ge=0, le=100)


@app.get('/health')
def health():
    return {'status': 'ok', 'model_version': app.state.metadata['version']}


@app.post('/predict')
def predict(data: Features):
    row = pd.DataFrame([data.model_dump()], columns=FEATURES)
    probability = float(app.state.model.predict_proba(row)[0, 1])
    return {'dropout_probability': probability, 'model_version': app.state.metadata['version']}


class ExplanationRequest(BaseModel):
    course_title: str = Field(min_length=1, max_length=200)
    current_topic: str = Field(min_length=1, max_length=300)
    completed_percent: float = Field(ge=0, le=100)


def result_store():
    return redis.Redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
                                decode_responses=True, socket_connect_timeout=1, socket_timeout=1)


@app.post('/explanations', status_code=202)
def create_explanation(data: ExplanationRequest):
    job_id = str(uuid4())
    store = result_store()
    try:
        store.setex(f'explanation:{job_id}', 86400, json.dumps({'status': 'queued'}))
        connection = pika.BlockingConnection(pika.URLParameters(os.getenv('AMQP_URL', 'amqp://guest:guest@localhost:5672/%2F')))
        try:
            channel = connection.channel()
            channel.queue_declare(queue='lesson_explanations', durable=True)
            channel.confirm_delivery()
            channel.basic_publish(exchange='', routing_key='lesson_explanations',
                                  body=json.dumps({'job_id': job_id, **data.model_dump()}),
                                  properties=pika.BasicProperties(delivery_mode=2), mandatory=True)
        finally:
            connection.close()
    except (redis.RedisError, pika.exceptions.AMQPError, OSError):
        try:
            store.delete(f'explanation:{job_id}')
        except redis.RedisError:
            pass
        raise HTTPException(status_code=503, detail='Queue or result store unavailable')
    return {'job_id': job_id, 'status': 'queued'}


@app.get('/explanations/{job_id}')
def get_explanation(job_id: UUID):
    try:
        value = result_store().get(f'explanation:{job_id}')
    except redis.RedisError:
        raise HTTPException(status_code=503, detail='Result store unavailable')
    if value is None:
        raise HTTPException(status_code=404, detail='Job not found')
    return json.loads(value)
