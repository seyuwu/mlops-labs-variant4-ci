"""Measure real single-node k3d behavior on a disposable hosted runner."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import statistics
import subprocess
import threading
import time
import requests

BASE = 'http://127.0.0.1:8080'
ML_HEADERS = {'Host': 'ml.localhost'}
FEATURES = {'attendance': .7, 'completed_percent': 65, 'weekly_hours': 4,
            'days_inactive': 3, 'prior_score': 75}
output = Path('cloud-evidence')
output.mkdir(exist_ok=True)


def kubectl(*args, check=True, timeout=120):
    return subprocess.run(['kubectl', *args], text=True, capture_output=True, check=check, timeout=timeout).stdout


def wait_http(path, *, headers=None, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = requests.get(BASE + path, headers=headers, timeout=2)
            if response.ok:
                return response
        except requests.RequestException:
            pass
        time.sleep(2)
    raise TimeoutError(path)


def deployment_ready(name, count, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = json.loads(kubectl('-n', 'lab4', 'get', 'deployment', name, '-o', 'json'))
        if state.get('status', {}).get('readyReplicas', 0) >= count:
            return
        time.sleep(2)
    raise TimeoutError(f'{name} did not reach {count} ready replicas')


def experiment(action, request, wait):
    samples = []
    stop = threading.Event()

    def monitor():
        while not stop.is_set():
            started = time.monotonic()
            try:
                response = request()
                ok = response.ok
            except requests.RequestException:
                ok = False
            samples.append({'t': round(started, 3), 'ok': ok})
            stop.wait(.2)

    thread = threading.Thread(target=monitor)
    thread.start()
    time.sleep(2)
    started = time.monotonic()
    try:
        action()
        wait()
        elapsed = time.monotonic() - started
        time.sleep(3)
    finally:
        stop.set()
        thread.join(timeout=5)
    failures = sum(not row['ok'] for row in samples)
    return {'duration_s': round(elapsed, 2), 'requests': len(samples), 'failures': failures,
            'sampling_interval_s': .2}


def p95(values):
    return sorted(values)[max(0, int(len(values) * .95 + .999999) - 1)]


wait_http('/health/ready')
deployment_ready('platform-api', 2)
distribution = {}
for _ in range(30):
    name = requests.get(BASE + '/whoami', timeout=3, headers={'Connection': 'close'}).json()['pod']
    distribution[name] = distribution.get(name, 0) + 1

pods = json.loads(kubectl('-n', 'lab4', 'get', 'pods', '-l', 'app=platform-api', '-o', 'json'))['items']
target = pods[0]['metadata']['name']
pod_failure = experiment(
    lambda: kubectl('-n', 'lab4', 'delete', 'pod', target, '--wait=false'),
    lambda: requests.get(BASE + '/health/ready', timeout=2),
    lambda: deployment_ready('platform-api', 2))

def rollout(name, image):
    kubectl('-n', 'lab4', 'set', 'image', 'deployment/' + name, 'api=' + image)
    kubectl('-n', 'lab4', 'rollout', 'status', 'deployment/' + name, '--timeout=180s')


api_rollout = experiment(
    lambda: rollout('platform-api', 'lab2-platform:v2'),
    lambda: requests.get(BASE + '/health/ready', timeout=2),
    lambda: deployment_ready('platform-api', 2))
versions = [requests.get(BASE + '/whoami', headers={'Connection': 'close'}, timeout=3).json()['version'] for _ in range(12)]

for i in range(20):
    response = requests.post(BASE + '/courses', json={'title': f'Load course {i}'}, timeout=5)
    response.raise_for_status()
cold, warm = [], []
headers_seen = {'hit': 0, 'miss': 0, 'other': 0}
for _ in range(20):
    kubectl('-n', 'lab4', 'exec', 'deployment/redis', '--', 'redis-cli', 'DEL', 'courses:v1')
    start = time.perf_counter()
    first = requests.get(BASE + '/courses', timeout=5)
    first.raise_for_status()
    cold.append(time.perf_counter() - start)
    start = time.perf_counter()
    second = requests.get(BASE + '/courses', timeout=5)
    second.raise_for_status()
    warm.append(time.perf_counter() - start)
    value = second.headers.get('X-Cache', 'other')
    headers_seen[value if value in headers_seen else 'other'] += 1

kubectl('-n', 'lab4', 'scale', 'deployment/platform-api', '--replicas=2')
deployment_ready('platform-api', 2)
load_stop = threading.Event()
load_result = {'ok': 0, 'errors': 0}
load_lock = threading.Lock()


def load_worker():
    session = requests.Session()
    session.trust_env = False
    while not load_stop.is_set():
        try:
            good = session.get(BASE + '/lab/cpu?iterations=300000', timeout=8).ok
        except requests.RequestException:
            good = False
        with load_lock:
            load_result['ok' if good else 'errors'] += 1


samples = []
with ThreadPoolExecutor(max_workers=4) as pool:
    futures = [pool.submit(load_worker) for _ in range(4)]
    start = time.monotonic()
    try:
        while time.monotonic() - start < 100:
            state = json.loads(kubectl('-n', 'lab4', 'get', 'hpa', 'platform-api', '-o', 'json'))
            status = state.get('status', {})
            samples.append({'elapsed_s': round(time.monotonic() - start, 1),
                            'current_replicas': status.get('currentReplicas'),
                            'desired_replicas': status.get('desiredReplicas'),
                            'metrics': status.get('currentMetrics', [])})
            time.sleep(5)
    finally:
        load_stop.set()
        for future in futures:
            future.result(timeout=15)

wait_http('/health', headers=ML_HEADERS)
deployment_ready('dropout-api', 2)
first_start = time.perf_counter()
first_response = requests.post(BASE + '/predict', headers=ML_HEADERS, json=FEATURES, timeout=10)
first_response.raise_for_status()
first_ms = (time.perf_counter() - first_start) * 1000
warm_latencies = []
for _ in range(20):
    start = time.perf_counter()
    response = requests.post(BASE + '/predict', headers=ML_HEADERS, json=FEATURES, timeout=10)
    response.raise_for_status()
    warm_latencies.append((time.perf_counter() - start) * 1000)
before_model = first_response.json()['model_version']
model_rollout = experiment(
    lambda: rollout('dropout-api', 'dropout-api:v2'),
    lambda: requests.post(BASE + '/predict', headers=ML_HEADERS, json=FEATURES, timeout=5),
    lambda: deployment_ready('dropout-api', 2))
deadline = time.monotonic() + 30
after_model = None
while time.monotonic() < deadline:
    after_model = requests.post(BASE + '/predict', headers={**ML_HEADERS, 'Connection': 'close'},
                                json=FEATURES, timeout=10).json()['model_version']
    if after_model == 'dropout-rf-v2':
        break
    time.sleep(1)
assert before_model == 'dropout-rf-v1' and after_model == 'dropout-rf-v2'

summary = {'node_track': 'single-node', 'distribution': distribution, 'pod_failure': pod_failure,
           'api_rollout': api_rollout, 'api_versions_after': versions,
           'cache': {'cold_p95_ms': round(p95(cold)*1000, 2), 'warm_p95_ms': round(p95(warm)*1000, 2),
                     'warm_response_headers': headers_seen},
           'hpa': {'samples': samples, 'load_requests': load_result},
           'model': {'before': before_model, 'after': after_model, 'rollout': model_rollout,
                     'first_ms': round(first_ms, 2), 'warm_median_ms': round(statistics.median(warm_latencies), 2)}}
(output / 'kubernetes.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
(output / 'kubernetes-resources.txt').write_text(kubectl('-n', 'lab4', 'get', 'all,pvc,ingress,hpa,pdb', '-o', 'wide'), encoding='utf-8')
(output / 'kubernetes-top.txt').write_text(kubectl('top', 'nodes', check=False), encoding='utf-8')
print(json.dumps(summary, indent=2))
