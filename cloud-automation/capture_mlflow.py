"""Render the actual five MLflow experiments on the hosted runner."""
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time

import requests
from playwright.sync_api import sync_playwright

root = Path.cwd()
lab = root / 'lab5-mlops'
out = root / 'cloud-evidence'
out.mkdir(exist_ok=True)
with sqlite3.connect(lab / 'mlruns.db') as database:
    row = database.execute("SELECT experiment_id FROM experiments WHERE name=?",
                           ('online-learning-dropout',)).fetchone()
    assert row is not None
    experiment_id = row[0]
    count = database.execute('SELECT COUNT(*) FROM runs WHERE experiment_id=?',
                             (experiment_id,)).fetchone()[0]
    assert count == 5, count

log = (out / 'mlflow-server.log').open('w', encoding='utf-8')
server = subprocess.Popen(['mlflow', 'ui', '--backend-store-uri', 'sqlite:///mlruns.db',
                           '--host', '127.0.0.1', '--port', '5500'], cwd=lab,
                          stdout=log, stderr=subprocess.STDOUT)
try:
    session = requests.Session()
    session.trust_env = False
    for attempt in range(60):
        try:
            if session.get('http://127.0.0.1:5500/', timeout=2).ok:
                break
        except requests.RequestException:
            pass
        time.sleep(1)
    else:
        raise RuntimeError('MLflow UI failed to start')
    chrome = shutil.which('google-chrome') or shutil.which('google-chrome-stable') or shutil.which('chromium')
    with sync_playwright() as playwright:
        options = {'headless': True, 'args': ['--no-sandbox']}
        if chrome:
            options['executable_path'] = chrome
        browser = playwright.chromium.launch(**options)
        page = browser.new_page(viewport={'width': 1600, 'height': 1000})
        page.goto(f'http://127.0.0.1:5500/#/experiments/{experiment_id}',
                  wait_until='domcontentloaded', timeout=45000)
        page.get_by_text('online-learning-dropout', exact=False).first.wait_for(timeout=45000)
        page.get_by_text('Model training', exact=True).first.click()
        page.wait_for_timeout(7000)
        (out / 'mlflow-visible.txt').write_text(page.locator('body').inner_text(), encoding='utf-8')
        page.screenshot(path=str(out / 'mlflow-before.png'), full_page=True)
        page.get_by_text('validation_f1', exact=False).first.wait_for(timeout=45000)
        page.wait_for_timeout(2500)
        page.screenshot(path=str(out / 'mlflow-experiments.png'), full_page=True)
        browser.close()
    print(f'Captured {count} actual MLflow runs in experiment {experiment_id}.')
finally:
    server.terminate()
    server.wait(timeout=15)
    log.close()
