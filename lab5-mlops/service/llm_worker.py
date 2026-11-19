"""Необязательный воркер: очередь -> Ollama -> результат в Redis."""
import json
import os
from time import perf_counter
from uuid import UUID
import httpx
import pika
import redis


def generate(job):
    prompt = (f"Курс: {job['course_title']}. Текущая тема: {job['current_topic']}. "
              f"Пройдено {job['completed_percent']:.0f}%. Предложи одну следующую тему урока "
              "в двух предложениях. Не выдумывай факты об обучающемся.")
    url = os.getenv('OLLAMA_URL', 'http://localhost:11434')
    model = os.getenv('LLM_MODEL', 'qwen2.5:0.5b')
    start = perf_counter()
    first_token = None
    text_parts = []
    last = {}
    with httpx.stream('POST', f'{url}/api/generate', timeout=120,
                      json={'model': model, 'prompt': prompt, 'stream': True,
                            'options': {'temperature': 0.3, 'num_predict': 120}}) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            last = json.loads(line)
            token = last.get('response', '')
            if token and first_token is None:
                first_token = perf_counter() - start
            text_parts.append(token)
    duration = last.get('eval_duration', 0) / 1e9
    return {'text': ''.join(text_parts), 'model': model, 'time_to_first_token_s': first_token,
            'tokens_per_second': last.get('eval_count', 0) / duration if duration else None,
            'total_s': perf_counter() - start}


def main():
    store = redis.Redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379/0'), decode_responses=True)
    connection = pika.BlockingConnection(pika.URLParameters(os.getenv('AMQP_URL', 'amqp://guest:guest@localhost:5672/%2F')))
    channel = connection.channel()
    channel.queue_declare(queue='lesson_explanations', durable=True)
    channel.basic_qos(prefetch_count=1)

    def consume(ch, method, _properties, body):
        key = None
        try:
            job = json.loads(body)
            key = f"explanation:{UUID(job['job_id'])}"
            existing = store.get(key)
            if existing and json.loads(existing).get('status') == 'done':
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return
            result = generate(job)
            store.setex(key, 86400, json.dumps({'status': 'done', **result}, ensure_ascii=False))
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as exc:
            if key:
                try:
                    store.setex(key, 86400, json.dumps({'status': 'failed', 'error': str(exc)}))
                except redis.RedisError:
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                    return
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    channel.basic_consume(queue='lesson_explanations', on_message_callback=consume, auto_ack=False)
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        connection.close()


if __name__ == '__main__':
    main()
