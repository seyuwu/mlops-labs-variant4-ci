"""Worker for durable RabbitMQ jobs. One JSON result per job id."""
import json
import os
from pathlib import Path
from uuid import UUID
import pika
from hashing import hash_file

ROOT = Path(os.getenv('INPUT_ROOT', 'sample_data')).resolve()
RESULTS = Path(os.getenv('RESULTS_DIR', 'results/jobs')).resolve()


def process(payload):
    job_id = str(UUID(payload['job_id']))
    file_path = (ROOT / payload['path']).resolve()
    file_path.relative_to(ROOT)
    RESULTS.mkdir(parents=True, exist_ok=True)
    destination = RESULTS / f'{job_id}.json'
    if destination.exists():
        return json.loads(destination.read_text(encoding='utf-8'))
    _, digest = hash_file(file_path)
    result = {'job_id': job_id, 'path': payload['path'], 'sha256': digest}
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(json.dumps(result), encoding='utf-8')
    temporary.replace(destination)
    return result


def main():
    connection = pika.BlockingConnection(pika.URLParameters(os.getenv('AMQP_URL', 'amqp://guest:guest@localhost:5672/%2F')))
    channel = connection.channel()
    channel.queue_declare(queue='file_hashes', durable=True)
    channel.basic_qos(prefetch_count=1)

    def handle(ch, method, _properties, body):
        try:
            print(json.dumps(process(json.loads(body))), flush=True)
        except Exception as exc:
            print(f'Invalid job: {exc}', flush=True)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return
        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue='file_hashes', on_message_callback=handle, auto_ack=False)
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        connection.close()


if __name__ == '__main__':
    main()
