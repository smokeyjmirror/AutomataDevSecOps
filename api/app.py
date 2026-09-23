import json
import os
import time
from typing import Optional

import psycopg2
from flask import Flask, jsonify, request
from flask_cors import CORS
from kafka import KafkaProducer
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
CORS(app)

DB_URL = os.environ.get('DATABASE_URL', 'postgresql://app_user:SecurePassword123!@localhost:5432/automata')
KAFKA_BOOTSTRAP_SERVERS = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')


def get_db_connection():
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)


def get_kafka_producer() -> Optional[KafkaProducer]:
    try:
        return KafkaProducer(
            bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
            value_serializer=lambda message: json.dumps(message).encode('utf-8'),
            api_version=(3, 7, 0),
        )
    except Exception:
        return None


def initialize_database():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL UNIQUE,
                    kind VARCHAR(50) NOT NULL,
                    capability TEXT NOT NULL,
                    rate_per_hour NUMERIC(10,2) NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'available'
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS clients (
                    id SERIAL PRIMARY KEY,
                    company_name VARCHAR(150) NOT NULL,
                    contact_email VARCHAR(150) NOT NULL UNIQUE,
                    account_status VARCHAR(20) NOT NULL DEFAULT 'active'
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id SERIAL PRIMARY KEY,
                    client_id INTEGER REFERENCES clients(id),
                    agent_id INTEGER REFERENCES agents(id),
                    task TEXT NOT NULL,
                    duration_hours INTEGER NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'queued',
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    completed_at TIMESTAMP
                );
                """
            )
            cur.execute(
                """
                INSERT INTO agents (name, kind, capability, rate_per_hour, status)
                VALUES
                    ('Atlas', 'Research Agent', 'Threat intelligence and reconnaissance', 85.00, 'available'),
                    ('Mira', 'Ops Agent', 'Infrastructure hardening and deployment support', 95.00, 'available'),
                    ('Nova', 'Content Agent', 'Policy summaries and internal documentation', 60.00, 'available')
                ON CONFLICT (name) DO NOTHING;
                """
            )
            cur.execute(
                """
                INSERT INTO clients (company_name, contact_email, account_status)
                VALUES
                    ('Apex Labs', 'ops@apexlabs.example', 'active'),
                    ('Northstar Secure', 'security@northstar.example', 'active'),
                    ('Blue Harbor', 'dm@blueharbor.example', 'active')
                ON CONFLICT (contact_email) DO NOTHING;
                """
            )
            conn.commit()


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'automata-api'}), 200


@app.route('/agents', methods=['GET'])
def get_agents():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM agents ORDER BY id;')
            return jsonify(cur.fetchall()), 200


@app.route('/clients', methods=['GET'])
def get_clients():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM clients ORDER BY id;')
            return jsonify(cur.fetchall()), 200


@app.route('/jobs', methods=['GET'])
def get_jobs():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT j.*, a.name AS agent_name, c.company_name AS client_name
                FROM jobs j
                LEFT JOIN agents a ON a.id = j.agent_id
                LEFT JOIN clients c ON c.id = j.client_id
                ORDER BY j.created_at DESC;
                """
            )
            return jsonify(cur.fetchall()), 200


@app.route('/jobs', methods=['POST'])
def create_job():
    payload = request.get_json() or {}
    client_id = payload.get('client_id')
    agent_id = payload.get('agent_id')
    task = payload.get('task')
    duration_hours = payload.get('duration_hours', 1)

    if not client_id or not agent_id or not task:
        return jsonify({'error': 'client_id, agent_id, and task are required'}), 400

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO jobs (client_id, agent_id, task, duration_hours, status, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, 'queued', NOW(), NOW())
                    RETURNING *;
                    """,
                    (client_id, agent_id, task, duration_hours),
                )
                job = cur.fetchone()
                conn.commit()

        producer = get_kafka_producer()
        if producer is not None:
            producer.send('automata.jobs', {'job_id': job['id'], 'status': 'queued'})
            producer.flush()

        return jsonify(job), 201
    except Exception as exc:  # pragma: no cover - debug surface for local dev
        return jsonify({'error': str(exc)}), 500


@app.route('/seed', methods=['POST'])
def seed_demo_data():
    initialize_database()
    return jsonify({'status': 'seeded'}), 200


if __name__ == '__main__':
    initialize_database()
    app.run(host='0.0.0.0', port=5000, debug=True)
