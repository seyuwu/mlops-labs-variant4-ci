"""Capture real public PR and RabbitMQ management pages on a hosted runner."""
import json
import os
from pathlib import Path
import re
import shutil
import time
from uuid import uuid4
import pika
import requests
from playwright.sync_api import sync_playwright

output = Path('cloud-evidence')
output.mkdir(exist_ok=True)
connection = pika.BlockingConnection(pika.URLParameters('amqp://guest:guest@127.0.0.1:5672/%2F'))
channel = connection.channel()
queue = 'lab3-screenshot-' + uuid4().hex[:8]
channel.queue_declare(queue=queue, auto_delete=True)
channel.basic_qos(prefetch_count=1)
for number in range(6):
    channel.basic_publish('', queue, json.dumps({'task': number}).encode())
channel.basic_consume(queue=queue, on_message_callback=lambda *_: None, auto_ack=False)
connection.process_data_events(time_limit=2)
session = requests.Session()
session.trust_env = False
for attempt in range(30):
    overview = session.get('http://127.0.0.1:15672/api/queues/%2F/' + queue,
                           auth=('guest', 'guest'), timeout=10)
    overview.raise_for_status()
    data = overview.json()
    if 'messages_ready' in data and data.get('consumers', 0) > 0:
        break
    time.sleep(1)
else:
    raise RuntimeError('RabbitMQ management statistics did not become available')
result = {'queue': queue, 'messages_ready': data['messages_ready'],
          'messages_unacknowledged': data['messages_unacknowledged'], 'consumers': data['consumers']}
assert result['messages_ready'] > 0 and result['consumers'] > 0
(output / 'rabbit-ui-data.json').write_text(json.dumps(result, indent=2), encoding='utf-8')

chrome = shutil.which('google-chrome') or shutil.which('google-chrome-stable') or shutil.which('chromium')
with sync_playwright() as playwright:
    options = {'headless': True, 'args': ['--no-sandbox']}
    if chrome:
        options['executable_path'] = chrome
    browser = playwright.chromium.launch(**options)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1)
    page.goto('http://127.0.0.1:15672/', wait_until='domcontentloaded', timeout=30000)
    page.locator('input[name="username"]').fill('guest')
    page.locator('input[name="password"]').fill('guest')
    page.locator('input[type="submit"],button[type="submit"]').first.click()
    page.goto('http://127.0.0.1:15672/#/queues', wait_until='domcontentloaded', timeout=30000)
    page.get_by_text(queue).first.wait_for(state='visible', timeout=30000)
    page.screenshot(path=str(output / 'rabbitmq-queue.png'), full_page=True)

    repo = os.environ['GITHUB_REPOSITORY']
    page.goto(f'https://github.com/{repo}/pull/1', wait_until='domcontentloaded', timeout=45000)
    page.wait_for_timeout(2500)
    target = page.get_by_text(re.compile('checks|merge|слияни', re.I)).last
    if target.count():
        target.scroll_into_view_if_needed(timeout=10000)
    page.screenshot(path=str(output / 'public-pr.png'), full_page=False)
    browser.close()
connection.close()
print('Captured RabbitMQ management and public PR pages:', json.dumps(result))
