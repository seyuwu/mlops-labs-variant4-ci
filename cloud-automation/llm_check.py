"""Measure ten real queued Ollama requests on the hosted runner."""
import json
from pathlib import Path
import re
import statistics
import subprocess
import time
import requests

url = 'http://127.0.0.1:8001'
session = requests.Session()
session.trust_env = False
deadline = time.monotonic() + 120
while True:
    try:
        if session.get(url + '/health', timeout=3).ok:
            break
    except requests.RequestException:
        pass
    if time.monotonic() >= deadline:
        raise TimeoutError('ML API unavailable')
    time.sleep(2)

features = {'attendance': .7, 'completed_percent': 65, 'weekly_hours': 4,
            'days_inactive': 3, 'prior_score': 75}
prediction_times = []
for _ in range(20):
    start = time.perf_counter()
    response = session.post(url + '/predict', json=features, timeout=10)
    response.raise_for_status()
    prediction_times.append(time.perf_counter() - start)

topics = [('Python', 'переменные'), ('Python', 'циклы'), ('Python', 'функции'),
          ('Базы данных', 'SELECT'), ('Базы данных', 'соединения таблиц'),
          ('Математика', 'производные'), ('Английский язык', 'Present Simple'),
          ('Git', 'ветки'), ('Docker', 'образы'), ('Машинное обучение', 'валидация')]
container_id = subprocess.check_output(['docker', 'compose', '-f', 'lab5-mlops/docker-compose.llm.yml',
                                        'ps', '-q', 'ollama'], text=True).strip()


def memory_megabytes():
    raw = subprocess.check_output(['docker', 'stats', '--no-stream', '--format', '{{.MemUsage}}', container_id],
                                  text=True, timeout=15).strip().split('/')[0].strip()
    match = re.match(r'([0-9.]+)\s*([KMG]i?B)', raw)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    return value * ({'KiB': 1/1024, 'MiB': 1, 'GiB': 1024, 'kB': 1/1000, 'MB': 1, 'GB': 1000}.get(unit, 1))


results = []
all_memory = []
for index, (course, topic) in enumerate(topics, 1):
    body = {'course_title': course, 'current_topic': topic, 'completed_percent': min(90, index * 9)}
    queued = session.post(url + '/explanations', json=body, timeout=15)
    queued.raise_for_status()
    assert queued.status_code == 202
    job_id = queued.json()['job_id']
    started = time.monotonic()
    last_memory = 0
    deadline = started + 240
    while time.monotonic() < deadline:
        response = session.get(url + '/explanations/' + job_id, timeout=10)
        response.raise_for_status()
        value = response.json()
        if value['status'] == 'done':
            break
        if value['status'] == 'failed':
            raise RuntimeError(value.get('error', 'LLM worker failed'))
        if time.monotonic() - last_memory >= 4:
            try:
                sample = memory_megabytes()
                if sample is not None:
                    all_memory.append(sample)
            except (subprocess.SubprocessError, ValueError):
                pass
            last_memory = time.monotonic()
        time.sleep(1)
    else:
        raise TimeoutError(f'LLM job {index} did not finish')
    results.append({'input': body, 'response': value['text'],
                    'time_to_first_token_s': value['time_to_first_token_s'],
                    'tokens_per_second': value['tokens_per_second'],
                    'total_s': value['total_s']})
    print(f"LLM {index}/10: {value['total_s']:.1f}s, first={value['time_to_first_token_s']}, speed={value['tokens_per_second']}", flush=True)

summary = {'model': 'qwen2.5:0.5b', 'requests': results,
           'prediction_median_ms': statistics.median(prediction_times)*1000,
           'ollama_sampled_peak_mib': max(all_memory) if all_memory else None,
           'memory_note': 'maximum of docker stats samples; may be below the true peak'}
Path('cloud-evidence').mkdir(exist_ok=True)
Path('cloud-evidence/llm.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'model': summary['model'], 'requests': len(results),
                  'prediction_median_ms': summary['prediction_median_ms'],
                  'ollama_sampled_peak_mib': summary['ollama_sampled_peak_mib']}, indent=2))
