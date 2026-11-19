import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

import io
import pytest
from fastapi.testclient import TestClient
from app import main
from app.db import Base, engine


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    with TestClient(main.app) as test_client:
        yield test_client


def create_examples(client):
    course = client.post('/courses', json={'title': 'Python', 'description': 'Основы'}).json()
    lesson = client.post('/lessons', json={'course_id': course['id'], 'title': 'Переменные'}).json()
    student = client.post('/students', json={'name': 'Анна', 'email': 'anna@example.org'}).json()
    return course, lesson, student


def test_courses_lessons_progress_and_validation(client):
    course, lesson, student = create_examples(client)
    assert client.get(f"/courses/{course['id']}/lessons").json()[0]['id'] == lesson['id']
    assert client.put(f"/courses/{course['id']}", json={'title': 'Python 2'}).json()['title'] == 'Python 2'
    progress = {'student_id': student['id'], 'lesson_id': lesson['id'], 'percent': 60}
    assert client.put('/progress', json=progress).json()['percent'] == 60
    progress['percent'] = 100
    assert client.put('/progress', json=progress).json()['percent'] == 100
    assert len(client.get(f"/students/{student['id']}/progress").json()) == 1
    assert client.get('/stats/popular').json()[0]['students'] == 1
    progress['percent'] = 101
    assert client.put('/progress', json=progress).status_code == 422
    assert client.post('/students', json={'name': 'Other', 'email': 'anna@example.org'}).status_code == 409
    assert client.delete(f"/courses/{course['id']}").status_code == 204
    assert client.get(f"/lessons/{lesson['id']}").status_code == 404


def test_quiz_does_not_expose_answer(client):
    _, lesson, _ = create_examples(client)
    response = client.post('/quizzes', json={'lesson_id': lesson['id'], 'question': '2+2?', 'correct_answer': '4'})
    assert response.status_code == 201
    assert 'correct_answer' not in response.json()
    quiz_id = response.json()['id']
    assert client.post(f'/quizzes/{quiz_id}/submit', json={'answer': '4'}).json() == {'correct': True}
    assert client.post(f'/quizzes/{quiz_id}/submit', json={'answer': '5'}).json() == {'correct': False}


def test_upload_download_with_storage_adapter(client, monkeypatch):
    class FakeResult:
        def __init__(self, value): self.value = value
        def stream(self, _size): yield self.value
        def close(self): pass
        def release_conn(self): pass

    class FakeMinio:
        def __init__(self): self.objects = {}
        def bucket_exists(self, _bucket): return True
        def put_object(self, _bucket, key, data, _length, **_kwargs): self.objects[key] = data.read()
        def get_object(self, _bucket, key): return FakeResult(self.objects[key])

    storage = FakeMinio()
    monkeypatch.setattr(main, 'storage_client', lambda: storage)
    _, lesson, _ = create_examples(client)
    response = client.post(f"/lessons/{lesson['id']}/files", files={'file': ('lesson.txt', io.BytesIO(b'lesson'), 'text/plain')})
    assert response.status_code == 201
    assert client.get(f"/files/{response.json()['id']}").content == b'lesson'


def test_health_openapi_and_metrics(client):
    assert client.get('/health/live').status_code == 200
    assert client.get('/health/ready').json()['status'] == 'ready'
    assert '/courses' in client.get('/openapi.json').json()['paths']
    assert 'platform_requests_total' in client.get('/metrics').text
    assert 'pod' in client.get('/whoami').json()
    assert client.get('/lab/cpu').status_code == 404


def test_cpu_load_is_explicitly_enabled(client, monkeypatch):
    monkeypatch.setenv('LAB_ENABLE_BENCHMARK', '1')
    assert client.get('/lab/cpu?iterations=10').json()['checksum'] == sum(i*i for i in range(10))
    assert client.get('/lab/cpu?iterations=1000001').status_code == 422


def test_course_cache_is_invalidated_on_changes(client, monkeypatch):
    class Cache:
        value = None
        def get(self, _key): return self.value
        def setex(self, _key, _ttl, value): self.value = value
        def delete(self, _key): self.value = None
    cache = Cache()
    monkeypatch.setattr(main, 'cache_client', lambda: cache)
    client.post('/courses', json={'title': 'First'})
    first = client.get('/courses')
    assert len(first.json()) == 1
    assert first.headers['X-Cache'] == 'miss'
    assert cache.value is not None
    assert client.get('/courses').headers['X-Cache'] == 'hit'
    client.post('/courses', json={'title': 'Second'})
    assert cache.value is None
    assert len(client.get('/courses').json()) == 2
