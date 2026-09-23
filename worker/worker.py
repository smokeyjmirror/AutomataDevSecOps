import json
import os
import time

import psycopg2
from kafka import KafkaConsumer

DB_URL = os.environ.get('DATABASE_URL', 'postgresql://app_user:SecurePassword123!@localhost:5432/automata')
KAFKA_BOOTSTRAP_SERVERS = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')


def get_db_connection():
    return psycopg2.connect(DB_URL)


def process_message(message):
    payload = message.value
    if isinstance(payload, bytes):
        payload = json.loads(payload.decode('utf-8'))

    job_id = payload.get('job_id')
    if not job_id:
        return

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE jobs
                SET status = 'completed', updated_at = NOW(), completed_at = NOW()
                WHERE id = %s;
                """,
                (job_id,),
            )
            conn.commit()

    print(f"Processed job {job_id}")


if __name__ == '__main__':
    consumer = KafkaConsumer(
        'automata.jobs',
        bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
        auto_offset_reset='earliest',
        enable_auto_commit=True,
        value_deserializer=lambda x: json.loads(x.decode('utf-8')) if x else None,
    )

    print('Worker listening for automata.jobs')
    for message in consumer:
        process_message(message)
