import json
import os
import sys
from uuid import uuid4
import pika


def main():
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python rabbit_producer.py part_0/file_00.bin')
    payload = {'job_id': str(uuid4()), 'path': sys.argv[1]}
    connection = pika.BlockingConnection(pika.URLParameters(os.getenv('AMQP_URL', 'amqp://guest:guest@localhost:5672/%2F')))
    channel = connection.channel()
    channel.queue_declare(queue='file_hashes', durable=True)
    channel.confirm_delivery()
    channel.basic_publish(exchange='', routing_key='file_hashes', body=json.dumps(payload),
                          properties=pika.BasicProperties(delivery_mode=2), mandatory=True)
    connection.close()
    print(json.dumps(payload))


if __name__ == '__main__':
    main()
