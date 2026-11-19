"""Exercise the real RabbitMQ producer/worker and acknowledgement modes."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from uuid import uuid4
import pika
import requests

root = Path('lab3-parallel').resolve()
sample = root / 'sample_data/part_0/file_00.bin'
sample.parent.mkdir(parents=True, exist_ok=True)
payload = b'file for actual RabbitMQ hash test'
sample.write_bytes(payload)
worker = subprocess.Popen([sys.executable, 'rabbit_worker.py'], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
try:
    time.sleep(2)
    producer = subprocess.run([sys.executable, 'rabbit_producer.py', 'part_0/file_00.bin'],
                              cwd=root, text=True, capture_output=True, check=True)
    job = json.loads(producer.stdout.strip())
    result_path = root / 'results/jobs' / (job['job_id'] + '.json')
    deadline = time.monotonic() + 40
    while not result_path.exists() and time.monotonic() < deadline:
        if worker.poll() is not None:
            raise RuntimeError('RabbitMQ worker stopped early: ' + worker.stdout.read())
        time.sleep(.5)
    result = json.loads(result_path.read_text(encoding='utf-8'))
    assert result['sha256'] == hashlib.sha256(payload).hexdigest()
finally:
    if worker.poll() is None:
        worker.send_signal(signal.SIGINT)
        try:
            worker.wait(timeout=10)
        except subprocess.TimeoutExpired:
            worker.terminate()
            worker.wait(timeout=5)

params = pika.URLParameters('amqp://guest:guest@127.0.0.1:5672/%2F')
connection = pika.BlockingConnection(params)
channel = connection.channel()
auto_queue = 'lab-auto-' + uuid4().hex[:8]
manual_queue = 'lab-manual-' + uuid4().hex[:8]
for name in (auto_queue, manual_queue):
    channel.queue_declare(queue=name)
    channel.basic_publish('', name, b'important task')
method, _, _ = channel.basic_get(auto_queue, auto_ack=True)
assert method is not None
connection.close()
connection = pika.BlockingConnection(params)
channel = connection.channel()
auto_remaining = channel.queue_declare(queue=auto_queue, passive=True).method.message_count
method, _, _ = channel.basic_get(manual_queue, auto_ack=False)
assert method is not None
connection.close()
connection = pika.BlockingConnection(params)
channel = connection.channel()
deadline = time.monotonic() + 15
while True:
    method, _, body = channel.basic_get(manual_queue, auto_ack=False)
    if method is not None:
        break
    if time.monotonic() > deadline:
        raise TimeoutError('Unacknowledged message was not returned')
    time.sleep(.2)
manual_redelivered = bool(method.redelivered)
channel.basic_ack(method.delivery_tag)
channel.queue_delete(auto_queue)
channel.queue_delete(manual_queue)
connection.close()
assert auto_remaining == 0 and manual_redelivered
management = requests.get('http://127.0.0.1:15672/api/overview', auth=('guest', 'guest'), timeout=10)
management.raise_for_status()
summary = {'hash_worker': 'passed', 'sha256': result['sha256'],
           'auto_ack_messages_after_disconnect': auto_remaining,
           'manual_ack_redelivered': manual_redelivered,
           'rabbitmq_version': management.json().get('rabbitmq_version')}
Path('cloud-evidence').mkdir(exist_ok=True)
Path('cloud-evidence/rabbitmq.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary, indent=2))
