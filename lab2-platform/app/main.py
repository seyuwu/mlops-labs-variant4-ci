from contextlib import asynccontextmanager
from io import BytesIO
import json
import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Response, UploadFile
from fastapi import Query
from fastapi.responses import StreamingResponse
from minio import Minio
import redis
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from . import models

REQUESTS = Counter('platform_requests_total', 'HTTP requests', ['method', 'route', 'status'])
LATENCY = Histogram('platform_request_seconds', 'HTTP request duration', ['route'])
PROGRESS_UPDATES = Counter('platform_progress_updates_total', 'Progress updates')
CACHE_EVENTS = Counter('platform_cache_events_total', 'Course cache lookups', ['result'])
BUCKET = os.getenv('MINIO_BUCKET', 'lesson-files')
MAX_UPLOAD = 16 * 1024 * 1024


@asynccontextmanager
async def lifespan(_app):
    if engine.dialect.name == 'postgresql':
        # Serialize initial schema creation when replicas start together.
        with engine.begin() as connection:
            connection.execute(text('SELECT pg_advisory_xact_lock(874201)'))
            Base.metadata.create_all(connection)
    else:
        Base.metadata.create_all(engine)
    yield


app = FastAPI(title='Платформа онлайн обучения', version='1.0.0', lifespan=lifespan)


@app.middleware('http')
async def metrics(request, call_next):
    start = perf_counter()
    response = await call_next(request)
    route = getattr(request.scope.get('route'), 'path', 'unmatched')
    REQUESTS.labels(request.method, route, str(response.status_code)).inc()
    LATENCY.labels(route).observe(perf_counter() - start)
    return response


class CourseInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=5000)


class LessonInput(BaseModel):
    course_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(default='', max_length=20000)


class StudentInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=254, pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class ProgressInput(BaseModel):
    student_id: int = Field(gt=0)
    lesson_id: int = Field(gt=0)
    percent: int = Field(ge=0, le=100)


class QuizInput(BaseModel):
    lesson_id: int = Field(gt=0)
    question: str = Field(min_length=1, max_length=2000)
    correct_answer: str = Field(min_length=1, max_length=1000)


class AnswerInput(BaseModel):
    answer: str = Field(min_length=1, max_length=1000)


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CourseOut(CourseInput, Output):
    id: int


class LessonOut(LessonInput, Output):
    id: int


class StudentOut(StudentInput, Output):
    id: int


class ProgressOut(ProgressInput, Output):
    id: int


def require(db, model, identifier):
    value = db.get(model, identifier)
    if value is None:
        raise HTTPException(status_code=404, detail=f'{model.__name__} not found')
    return value


def persist(db, value):
    db.add(value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Conflict with existing data')
    db.refresh(value)
    return value


def cache_client():
    url = os.getenv('REDIS_URL')
    return redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=0.3, socket_timeout=0.3) if url else None


def invalidate_courses():
    client = cache_client()
    if client:
        try:
            client.delete('courses:v1')
        except redis.RedisError:
            pass


@app.get('/health/live')
def live():
    return {'status': 'ok'}


@app.get('/whoami')
def whoami():
    return {'pod': os.getenv('HOSTNAME', 'local'), 'version': os.getenv('APP_VERSION', 'local')}


@app.get('/lab/cpu', include_in_schema=False)
def cpu_load(iterations: int = Query(default=300000, ge=1, le=1000000)):
    if os.getenv('LAB_ENABLE_BENCHMARK') != '1':
        raise HTTPException(status_code=404, detail='Not found')
    value = 0
    for index in range(iterations):
        value = (value + index * index) % 1000000007
    return {'checksum': value}


@app.get('/health/ready')
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text('SELECT 1'))
    except Exception:
        raise HTTPException(status_code=503, detail='Database unavailable')
    return {'status': 'ready'}


@app.get('/metrics', include_in_schema=False)
def metrics_endpoint():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post('/courses', response_model=CourseOut, status_code=201)
def create_course(data: CourseInput, db: Session = Depends(get_db)):
    result = persist(db, models.Course(**data.model_dump()))
    invalidate_courses()
    return result


@app.get('/courses', response_model=list[CourseOut])
def courses(response: Response, db: Session = Depends(get_db)):
    client = cache_client()
    cache_status = 'disabled' if client is None else 'miss'
    if client:
        try:
            cached = client.get('courses:v1')
            if cached is not None:
                CACHE_EVENTS.labels('hit').inc()
                response.headers['X-Cache'] = 'hit'
                return json.loads(cached)
        except (redis.RedisError, ValueError):
            cache_status = 'unavailable'
    result = list(db.scalars(select(models.Course).order_by(models.Course.id)))
    CACHE_EVENTS.labels('miss').inc()
    if client:
        try:
            client.setex('courses:v1', 30, json.dumps([CourseOut.model_validate(item).model_dump() for item in result]))
        except redis.RedisError:
            cache_status = 'unavailable'
    response.headers['X-Cache'] = cache_status
    return result


@app.get('/courses/{course_id}', response_model=CourseOut)
def get_course(course_id: int, db: Session = Depends(get_db)):
    return require(db, models.Course, course_id)


@app.put('/courses/{course_id}', response_model=CourseOut)
def update_course(course_id: int, data: CourseInput, db: Session = Depends(get_db)):
    course = require(db, models.Course, course_id)
    for key, value in data.model_dump().items():
        setattr(course, key, value)
    result = persist(db, course)
    invalidate_courses()
    return result


@app.delete('/courses/{course_id}', status_code=204)
def delete_course(course_id: int, db: Session = Depends(get_db)):
    db.delete(require(db, models.Course, course_id))
    db.commit()
    invalidate_courses()
    return Response(status_code=204)


@app.post('/lessons', response_model=LessonOut, status_code=201)
def create_lesson(data: LessonInput, db: Session = Depends(get_db)):
    require(db, models.Course, data.course_id)
    return persist(db, models.Lesson(**data.model_dump()))


@app.get('/courses/{course_id}/lessons', response_model=list[LessonOut])
def lessons(course_id: int, db: Session = Depends(get_db)):
    require(db, models.Course, course_id)
    return list(db.scalars(select(models.Lesson).where(models.Lesson.course_id == course_id)))


@app.get('/lessons/{lesson_id}', response_model=LessonOut)
def get_lesson(lesson_id: int, db: Session = Depends(get_db)):
    return require(db, models.Lesson, lesson_id)


@app.put('/lessons/{lesson_id}', response_model=LessonOut)
def update_lesson(lesson_id: int, data: LessonInput, db: Session = Depends(get_db)):
    lesson = require(db, models.Lesson, lesson_id)
    require(db, models.Course, data.course_id)
    for key, value in data.model_dump().items():
        setattr(lesson, key, value)
    return persist(db, lesson)


@app.delete('/lessons/{lesson_id}', status_code=204)
def delete_lesson(lesson_id: int, db: Session = Depends(get_db)):
    db.delete(require(db, models.Lesson, lesson_id))
    db.commit()
    return Response(status_code=204)


@app.post('/students', response_model=StudentOut, status_code=201)
def create_student(data: StudentInput, db: Session = Depends(get_db)):
    return persist(db, models.Student(**data.model_dump()))


@app.get('/students', response_model=list[StudentOut])
def students(db: Session = Depends(get_db)):
    return list(db.scalars(select(models.Student).order_by(models.Student.id)))


@app.get('/students/{student_id}', response_model=StudentOut)
def get_student(student_id: int, db: Session = Depends(get_db)):
    return require(db, models.Student, student_id)


@app.put('/students/{student_id}', response_model=StudentOut)
def update_student(student_id: int, data: StudentInput, db: Session = Depends(get_db)):
    student = require(db, models.Student, student_id)
    for key, value in data.model_dump().items():
        setattr(student, key, value)
    return persist(db, student)


@app.delete('/students/{student_id}', status_code=204)
def delete_student(student_id: int, db: Session = Depends(get_db)):
    db.delete(require(db, models.Student, student_id))
    db.commit()
    return Response(status_code=204)


@app.put('/progress', response_model=ProgressOut)
def set_progress(data: ProgressInput, db: Session = Depends(get_db)):
    require(db, models.Student, data.student_id)
    require(db, models.Lesson, data.lesson_id)
    progress = db.scalar(select(models.Progress).where(
        models.Progress.student_id == data.student_id, models.Progress.lesson_id == data.lesson_id))
    if progress is None:
        progress = models.Progress(**data.model_dump())
    else:
        progress.percent = data.percent
    result = persist(db, progress)
    PROGRESS_UPDATES.inc()
    return result


@app.get('/students/{student_id}/progress', response_model=list[ProgressOut])
def get_progress(student_id: int, db: Session = Depends(get_db)):
    require(db, models.Student, student_id)
    return list(db.scalars(select(models.Progress).where(models.Progress.student_id == student_id)))


@app.post('/quizzes', status_code=201)
def create_quiz(data: QuizInput, db: Session = Depends(get_db)):
    require(db, models.Lesson, data.lesson_id)
    quiz = persist(db, models.Quiz(**data.model_dump()))
    return {'id': quiz.id, 'lesson_id': quiz.lesson_id, 'question': quiz.question}


@app.post('/quizzes/{quiz_id}/submit')
def submit_quiz(quiz_id: int, data: AnswerInput, db: Session = Depends(get_db)):
    quiz = require(db, models.Quiz, quiz_id)
    return {'correct': data.answer.strip().casefold() == quiz.correct_answer.strip().casefold()}


def storage_client():
    return Minio(os.getenv('MINIO_ENDPOINT', 'localhost:9000'),
                 access_key=os.getenv('MINIO_ACCESS_KEY', 'minioadmin'),
                 secret_key=os.getenv('MINIO_SECRET_KEY', 'minioadmin'),
                 secure=os.getenv('MINIO_SECURE', 'false').lower() == 'true')


@app.post('/lessons/{lesson_id}/files', status_code=201)
async def upload_file(lesson_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    require(db, models.Lesson, lesson_id)
    content = await file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail='File exceeds 16 MiB')
    original_name = Path(file.filename or 'file').name[:255]
    key = f'lessons/{lesson_id}/{uuid4().hex}'
    content_type = file.content_type or 'application/octet-stream'
    client = storage_client()
    try:
        if not client.bucket_exists(BUCKET):
            client.make_bucket(BUCKET)
        client.put_object(BUCKET, key, BytesIO(content), len(content), content_type=content_type)
    except Exception:
        raise HTTPException(status_code=503, detail='Object storage unavailable')
    item = persist(db, models.LessonFile(lesson_id=lesson_id, object_key=key,
                                        original_name=original_name, content_type=content_type))
    return {'id': item.id, 'name': item.original_name, 'size': len(content)}


@app.get('/files/{file_id}')
def download_file(file_id: int, db: Session = Depends(get_db)):
    item = require(db, models.LessonFile, file_id)
    try:
        result = storage_client().get_object(BUCKET, item.object_key)
    except Exception:
        raise HTTPException(status_code=503, detail='Object storage unavailable')

    def stream():
        try:
            yield from result.stream(64 * 1024)
        finally:
            result.close()
            result.release_conn()
    return StreamingResponse(stream(), media_type=item.content_type)


@app.get('/stats/popular')
def popular(db: Session = Depends(get_db)):
    statement = (select(models.Course.id, models.Course.title, func.count(func.distinct(models.Progress.student_id)))
                 .outerjoin(models.Lesson, models.Lesson.course_id == models.Course.id)
                 .outerjoin(models.Progress, models.Progress.lesson_id == models.Lesson.id)
                 .group_by(models.Course.id, models.Course.title).order_by(func.count(func.distinct(models.Progress.student_id)).desc()))
    return [{'course_id': row[0], 'title': row[1], 'students': row[2]} for row in db.execute(statement)]
