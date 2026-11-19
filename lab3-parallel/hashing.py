"""Вариант 4: SHA-256 файлов и поиск дубликатов с повторяемыми замерами."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import random
from statistics import median
from time import perf_counter

ROOT = Path(__file__).parent
DATA = ROOT / 'sample_data'


def generate_data():
    paths = []
    for i in range(48):
        folder = DATA / f'part_{i % 4}'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f'file_{i:02d}.bin'
        # Eight files intentionally repeat the first eight files.
        seed = i if i < 40 else i - 40
        path.write_bytes(random.Random(seed).randbytes(256 * 1024))
        paths.append(path)
    return paths


def hash_file(path):
    digest = sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(128 * 1024), b''):
            digest.update(block)
    return str(path), digest.hexdigest()


def duplicates(results):
    groups = defaultdict(list)
    for path, digest in results:
        groups[digest].append(Path(path).name)
    return sorted([sorted(paths) for paths in groups.values() if len(paths) > 1])


def execute(paths, mode, workers):
    if mode == 'sequential':
        return list(map(hash_file, paths))
    pool_type = ThreadPoolExecutor if mode == 'threads' else ProcessPoolExecutor
    with pool_type(max_workers=workers) as pool:
        return list(pool.map(hash_file, paths))


def run():
    paths = generate_data()
    expected = sorted(execute(paths, 'sequential', 1))
    found = duplicates(expected)
    assert len(found) == 8
    measurements = {}
    for mode, workers in [('sequential', 1)] + [(mode, n) for mode in ('threads', 'processes') for n in (1, 2, 4)]:
        samples = []
        for _ in range(3):
            start = perf_counter()
            actual = sorted(execute(paths, mode, workers))
            samples.append(perf_counter() - start)
            assert actual == expected
        measurements[f'{mode}_{workers}'] = {'samples_s': samples, 'median_s': median(samples)}
    results = {'files': len(paths), 'size_bytes': sum(p.stat().st_size for p in paths),
               'duplicate_groups': found, 'measurements': measurements}
    output = ROOT / 'results' / 'hashing.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    run()
