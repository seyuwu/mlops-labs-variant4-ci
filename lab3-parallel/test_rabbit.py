from hashlib import sha256
from uuid import uuid4
import pytest
import rabbit_worker


def test_worker_is_idempotent_and_rejects_path_escape(tmp_path, monkeypatch):
    inputs = tmp_path / 'inputs'
    inputs.mkdir()
    data = inputs / 'file.bin'
    data.write_bytes(b'lesson file')
    monkeypatch.setattr(rabbit_worker, 'ROOT', inputs.resolve())
    monkeypatch.setattr(rabbit_worker, 'RESULTS', tmp_path / 'results')
    payload = {'job_id': str(uuid4()), 'path': 'file.bin'}
    result = rabbit_worker.process(payload)
    assert result['sha256'] == sha256(b'lesson file').hexdigest()
    data.write_bytes(b'changed after completion')
    assert rabbit_worker.process(payload) == result
    with pytest.raises(ValueError):
        rabbit_worker.process({'job_id': str(uuid4()), 'path': '../outside.bin'})
