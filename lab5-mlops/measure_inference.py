import json
from pathlib import Path
from statistics import median
from time import perf_counter
from fastapi.testclient import TestClient
from service.app import app

features = {'attendance': 0.7, 'completed_percent': 65, 'weekly_hours': 4,
            'days_inactive': 3, 'prior_score': 75}
with TestClient(app) as client:
    samples = []
    for _ in range(30):
        start = perf_counter()
        response = client.post('/predict', json=features)
        samples.append(perf_counter() - start)
        response.raise_for_status()
    ordered = sorted(samples)
    result = {'sample': features, 'response': response.json(), 'requests': len(samples),
              'median_s': median(samples), 'p95_s': ordered[28],
              'method': 'FastAPI TestClient, in-process; includes request handling'}
Path('reports/inference.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
