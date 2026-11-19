from fastapi.testclient import TestClient
from service import app as app_module

app = app_module.app


def test_prediction_and_validation():
    with TestClient(app) as client:
        body = {'attendance': 0.7, 'completed_percent': 65, 'weekly_hours': 4,
                'days_inactive': 3, 'prior_score': 75}
        response = client.post('/predict', json=body)
        assert response.status_code == 200
        assert 0 <= response.json()['dropout_probability'] <= 1
        assert response.json()['model_version']
        body['attendance'] = 2
        assert client.post('/predict', json=body).status_code == 422


def test_explanation_is_queued_and_can_be_polled(monkeypatch):
    class Store:
        def __init__(self): self.values = {}
        def setex(self, key, _ttl, value): self.values[key] = value
        def get(self, key): return self.values.get(key)
        def delete(self, key): self.values.pop(key, None)

    class Channel:
        def queue_declare(self, **_kwargs): pass
        def confirm_delivery(self): pass
        def basic_publish(self, **_kwargs): pass

    class Connection:
        def channel(self): return Channel()
        def close(self): pass

    store = Store()
    monkeypatch.setattr(app_module, 'result_store', lambda: store)
    monkeypatch.setattr(app_module.pika, 'BlockingConnection', lambda *_args: Connection())
    with TestClient(app) as client:
        result = client.post('/explanations', json={'course_title': 'Python', 'current_topic': 'Циклы', 'completed_percent': 50})
        assert result.status_code == 202
        assert client.get('/explanations/' + result.json()['job_id']).json() == {'status': 'queued'}
