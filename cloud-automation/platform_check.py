"""End-to-end checks against the actual Docker Compose services."""
import json
from pathlib import Path
from time import sleep, monotonic
from uuid import uuid4
import requests

base = 'http://127.0.0.1:8080'
session = requests.Session()
session.trust_env = False
deadline = monotonic() + 120
while True:
    try:
        if session.get(base + '/health/ready', timeout=3).status_code == 200:
            break
    except requests.RequestException:
        pass
    if monotonic() > deadline:
        raise TimeoutError('API did not become ready')
    sleep(2)


def send(method, path, **kwargs):
    response = session.request(method, base + path, timeout=15, **kwargs)
    response.raise_for_status()
    return response


course = send('POST', '/courses', json={'title': 'Учебный курс', 'description': 'Проверка Compose'}).json()
lesson = send('POST', '/lessons', json={'course_id': course['id'], 'title': 'Первый урок'}).json()
student = send('POST', '/students', json={'name': 'Тестовый студент',
    'email': f'{uuid4().hex}@example.org'}).json()
progress = send('PUT', '/progress', json={'student_id': student['id'], 'lesson_id': lesson['id'], 'percent': 75}).json()
quiz = send('POST', '/quizzes', json={'lesson_id': lesson['id'], 'question': '2+2?', 'correct_answer': '4'}).json()
assert send('POST', f"/quizzes/{quiz['id']}/submit", json={'answer': '4'}).json()['correct']
payload = b'Online-learning file verified through real MinIO.'
upload = send('POST', f"/lessons/{lesson['id']}/files",
              files={'file': ('lesson.txt', payload, 'text/plain')}).json()
assert send('GET', f"/files/{upload['id']}").content == payload
assert progress['percent'] == 75
assert 'platform_requests_total' in send('GET', '/metrics').text
assert '/courses' in send('GET', '/openapi.json').json()['paths']

prometheus = session.get('http://127.0.0.1:9090/-/healthy', timeout=10)
prometheus.raise_for_status()
grafana = session.get('http://127.0.0.1:3000/api/health', timeout=10)
grafana.raise_for_status()
dashboard = session.get('http://127.0.0.1:3000/api/dashboards/uid/learning-platform',
                        auth=('admin', 'local-lab-password'), timeout=10)
dashboard.raise_for_status()
rules = session.get('http://127.0.0.1:9090/api/v1/rules', timeout=10)
rules.raise_for_status()
assert any(group.get('rules') for group in rules.json()['data']['groups'])
result = {'api': 'healthy', 'course_id': course['id'], 'lesson_id': lesson['id'],
          'student_id': student['id'], 'progress_percent': progress['percent'],
          'quiz': 'correct answer accepted', 'minio_upload_download': 'passed',
          'prometheus': prometheus.status_code, 'grafana': grafana.status_code,
          'dashboard_title': dashboard.json()['dashboard']['title'], 'alert_rule': 'loaded'}
Path('cloud-evidence').mkdir(exist_ok=True)
Path('cloud-evidence/platform.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
