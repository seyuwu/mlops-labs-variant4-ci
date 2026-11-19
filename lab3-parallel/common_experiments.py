"""Общие опыты по параллелизму; результаты записываются в JSON."""
import asyncio
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from queue import Queue
from statistics import median
from threading import Barrier, Lock, Thread
from time import perf_counter, sleep
from urllib.request import urlopen


def cpu_work(count):
    value = 0
    for i in range(count):
        value = (value + i * i) % 1000000007
    return value


def measure(call, repetitions=3):
    samples = []
    for _ in range(repetitions):
        start = perf_counter()
        call()
        samples.append(perf_counter() - start)
    return {"samples_s": samples, "median_s": median(samples)}


def cpu_comparison():
    tasks = [250000] * 4

    def sequence():
        return list(map(cpu_work, tasks))

    def pool(pool_type, workers):
        with pool_type(max_workers=workers) as executor:
            return list(executor.map(cpu_work, tasks))

    expected = sequence()
    assert pool(ThreadPoolExecutor, 4) == expected
    assert pool(ProcessPoolExecutor, 4) == expected
    results = {"sequential": measure(sequence)}
    for workers in (1, 2, 4):
        results[f"threads_{workers}"] = measure(lambda: pool(ThreadPoolExecutor, workers))
        results[f"processes_{workers}"] = measure(lambda: pool(ProcessPoolExecutor, workers))
    return results


class SlowHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        sleep(0.025)
        body = b'OK'
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


async def async_requests(port, count, concurrency):
    semaphore = asyncio.Semaphore(concurrency)

    async def request():
        async with semaphore:
            reader, writer = await asyncio.open_connection('127.0.0.1', port)
            writer.write(b'GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
            await writer.drain()
            response = await reader.read()
            writer.close()
            await writer.wait_closed()
            assert response.endswith(b'OK')

    await asyncio.gather(*(request() for _ in range(count)))


def io_comparison():
    server = ThreadingHTTPServer(('127.0.0.1', 0), SlowHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    count = 30

    def synchronous():
        for _ in range(count):
            with urlopen(f'http://127.0.0.1:{port}/', timeout=5) as response:
                assert response.read() == b'OK'

    try:
        results = {"synchronous": measure(synchronous)}
        for concurrency in (1, 5, 10):
            results[f"async_{concurrency}"] = measure(
                lambda: asyncio.run(async_requests(port, count, concurrency)))
        return results
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


async def event_loop_experiment(use_thread):
    ticks = []

    async def heartbeat():
        deadline = perf_counter() + 0.3
        while perf_counter() < deadline:
            await asyncio.sleep(0.01)
            ticks.append(perf_counter())

    async def slow_operation():
        await asyncio.sleep(0.03)
        if use_thread:
            await asyncio.to_thread(sleep, 0.15)
        else:
            sleep(0.15)

    await asyncio.gather(heartbeat(), slow_operation())
    return max((later - earlier for earlier, later in zip(ticks, ticks[1:])), default=0)


def counter_experiment(protected, workers=4, iterations=200):
    shared = [0]
    barrier = Barrier(workers)
    lock = Lock()

    def worker():
        for _ in range(iterations):
            if protected:
                with lock:
                    shared[0] += 1
                barrier.wait()
            else:
                value = shared[0]
                barrier.wait()
                shared[0] = value + 1
            barrier.wait()

    threads = [Thread(target=worker) for _ in range(workers)]
    start = perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return {"actual": shared[0], "expected": workers * iterations,
            "elapsed_s": perf_counter() - start}


def queue_experiment(values, workers=3):
    queue = Queue()
    output = []
    lock = Lock()

    def consume():
        while True:
            value = queue.get()
            try:
                if value is None:
                    return
                result = cpu_work(value)
                with lock:
                    output.append(result)
            finally:
                queue.task_done()

    threads = [Thread(target=consume) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for value in values:
        queue.put(value)
    for _ in threads:
        queue.put(None)
    queue.join()
    for thread in threads:
        thread.join()
    return sorted(output)


def main():
    race_runs = [counter_experiment(False) for _ in range(3)]
    lock_runs = [counter_experiment(True) for _ in range(3)]
    assert all(run['actual'] < run['expected'] for run in race_runs)
    assert all(run['actual'] == run['expected'] for run in lock_runs)
    race = {**race_runs[0], 'samples_s': [r['elapsed_s'] for r in race_runs],
            'median_s': median(r['elapsed_s'] for r in race_runs)}
    protected = {**lock_runs[0], 'samples_s': [r['elapsed_s'] for r in lock_runs],
                 'median_s': median(r['elapsed_s'] for r in lock_runs)}
    values = [5000, 6000, 7000]
    assert queue_experiment(values) == sorted(map(cpu_work, values))
    results = {
        "cpu": cpu_comparison(),
        "io": io_comparison(),
        "event_loop": {
            "blocking_max_gap_s": asyncio.run(event_loop_experiment(False)),
            "to_thread_max_gap_s": asyncio.run(event_loop_experiment(True)),
        },
        "race": race,
        "lock": protected,
        "queue": {"tasks": len(values), "completed": len(queue_experiment(values))},
    }
    output = Path(__file__).parent / 'results' / 'common.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
