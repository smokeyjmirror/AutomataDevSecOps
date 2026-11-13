import json
import os
import secrets
import time
from datetime import timedelta
from functools import wraps
from typing import Optional
from urllib.parse import urlsplit

import jwt
import psycopg2
import requests
from flask import Flask, jsonify, redirect, request, session
from flask_cors import CORS
from kafka import KafkaProducer
from psycopg2.extras import RealDictCursor

from inventory_assistant import answer_inventory_query
from oidc_auth import OIDCConfig

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY')
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('SESSION_COOKIE_SECURE', '').lower()
    in {'1', 'true', 'yes', 'on'},
    PERMANENT_SESSION_LIFETIME=timedelta(hours=1),
)
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        'FRONTEND_ORIGINS', 'http://localhost:8000,http://localhost:8001'
    ).split(',')
    if origin.strip()
]
CORS(app, origins=FRONTEND_ORIGINS, supports_credentials=True)
OIDC = OIDCConfig.from_env()

DB_CONFIG = {
    'host': os.environ.get('PGHOST', 'localhost'),
    'dbname': os.environ.get('PGDATABASE', 'automata'),
    'user': os.environ.get('PGUSER', 'app_user'),
    'password': os.environ.get('PGPASSWORD'),
}
KAFKA_BOOTSTRAP_SERVERS = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


def get_kafka_producer() -> Optional[KafkaProducer]:
    try:
        return KafkaProducer(
            bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
            value_serializer=lambda message: json.dumps(message).encode('utf-8'),
            api_version=(3, 7, 0),
        )
    except Exception:
        return None


def current_identity():
    identity = session.get('identity')
    return identity if isinstance(identity, dict) else None


def require_roles(*allowed_roles):
    def decorator(handler):
        @wraps(handler)
        def wrapped(*args, **kwargs):
            identity = current_identity()
            if identity is None:
                return jsonify({'error': 'Authentication required'}), 401
            if not set(identity.get('roles', [])).intersection(allowed_roles):
                return jsonify({'error': 'Insufficient permissions'}), 403
            return handler(*args, **kwargs)

        return wrapped

    return decorator


def configured_oidc_metadata():
    if not app.secret_key:
        raise RuntimeError('FLASK_SECRET_KEY must be configured for OIDC sessions')
    return OIDC.load_metadata()


def allowed_return_origin(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if (
        parsed.scheme not in {'http', 'https'}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.path not in {'', '/'}
        or parsed.query
        or parsed.fragment
    ):
        return None
    origin = f'{parsed.scheme}://{parsed.netloc}'
    return origin if origin in FRONTEND_ORIGINS else None


def get_active_client_for_identity(identity):
    email = identity.get('email')
    if not isinstance(email, str):
        return None
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, company_name, contact_email
                FROM clients
                WHERE LOWER(contact_email) = %s AND account_status = 'active';
                """,
                (email,),
            )
            return cur.fetchone()


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
                CREATE TABLE IF NOT EXISTS inventory_items (
                    id SERIAL PRIMARY KEY,
                    sku VARCHAR(50) NOT NULL UNIQUE,
                    name VARCHAR(150) NOT NULL UNIQUE,
                    quantity INTEGER NOT NULL CHECK (quantity >= 0),
                    reorder_point INTEGER NOT NULL CHECK (reorder_point >= 0),
                    target_stock INTEGER NOT NULL CHECK (target_stock >= reorder_point)
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
            cur.execute(
                """
                INSERT INTO inventory_items (sku, name, quantity, reorder_point, target_stock)
                VALUES
                    ('FLT-100', 'Nebula Filter', 4, 5, 20),
                    ('CRY-210', 'Cryo Cell', 18, 6, 24),
                    ('SEAL-305', 'Docking Seal', 7, 10, 30),
                    ('CAB-440', 'Quantum Cable', 42, 12, 48),
                    ('SEN-520', 'Cargo Sensor', 0, 4, 16)
                ON CONFLICT (sku) DO NOTHING;
                """
            )
            conn.commit()


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'automata-api'}), 200


@app.route('/auth/login', methods=['GET'])
def login():
    return_origin = allowed_return_origin(request.args.get('return_to'))
    if return_origin is None:
        return jsonify({'error': 'return_to must be an allowed frontend origin'}), 400

    try:
        metadata = configured_oidc_metadata()
        authorization_url, login_state = OIDC.authorization_url(
            metadata, OIDC.redirect_uri
        )
    except (requests.RequestException, RuntimeError, ValueError):
        app.logger.exception('Unable to start OIDC authorization')
        return jsonify({'error': 'OIDC provider is unavailable or misconfigured'}), 503

    session.clear()
    session['oidc_login'] = login_state
    session['return_to'] = return_origin
    return redirect(authorization_url)


@app.route('/auth/callback', methods=['GET'])
def oidc_callback():
    if request.args.get('error'):
        session.clear()
        return jsonify({'error': 'OIDC sign-in was not completed'}), 401

    login_state = session.get('oidc_login')
    state = request.args.get('state')
    code = request.args.get('code')
    expected_state = login_state.get('state') if isinstance(login_state, dict) else None
    if (
        not isinstance(login_state, dict)
        or not isinstance(state, str)
        or not isinstance(expected_state, str)
        or not secrets.compare_digest(state, expected_state)
        or not isinstance(code, str)
        or not code
        or not isinstance(login_state.get('nonce'), str)
        or not isinstance(login_state.get('code_verifier'), str)
    ):
        session.clear()
        return jsonify({'error': 'OIDC state or authorization code is invalid'}), 400

    return_origin = allowed_return_origin(session.get('return_to'))
    if return_origin is None:
        session.clear()
        return jsonify({'error': 'OIDC return destination is invalid'}), 400

    try:
        metadata = configured_oidc_metadata()
        token_response = OIDC.exchange_code(
            metadata, code, login_state['code_verifier']
        )
        claims = OIDC.validate_id_token(
            metadata, token_response['id_token'], login_state['nonce']
        )
    except (requests.RequestException, RuntimeError, ValueError, jwt.PyJWTError):
        app.logger.exception('OIDC authorization callback failed')
        session.clear()
        return jsonify({'error': 'OIDC sign-in could not be validated'}), 401

    subject = claims.get('sub')
    roles = OIDC.roles_from_claims(claims)
    if not isinstance(subject, str) or not subject:
        session.clear()
        return jsonify({'error': 'OIDC identity is missing a subject'}), 401
    if not set(roles).intersection({OIDC.customer_role, OIDC.staff_role}):
        session.clear()
        return jsonify({'error': 'OIDC identity has no application role'}), 403

    session.clear()
    session.permanent = True
    session['identity'] = {
        'sub': subject,
        'email': OIDC.email_from_claims(claims),
        'roles': roles,
    }
    return redirect(return_origin)


@app.route('/auth/me', methods=['GET'])
def get_authenticated_identity():
    identity = current_identity()
    if identity is None:
        return jsonify({'error': 'Authentication required'}), 401
    return jsonify(identity), 200


@app.route('/auth/logout', methods=['POST'])
def logout():
    return_origin = allowed_return_origin(request.args.get('return_to'))
    if return_origin is None:
        return jsonify({'error': 'return_to must be an allowed frontend origin'}), 400

    session.clear()
    try:
        metadata = OIDC.load_metadata()
        redirect_url = OIDC.logout_url(metadata, return_origin)
    except (requests.RequestException, RuntimeError, ValueError):
        app.logger.exception('OIDC provider logout is unavailable')
        redirect_url = None
    return jsonify({'redirect_url': redirect_url or return_origin}), 200


@app.route('/agents', methods=['GET'])
def get_agents():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM agents ORDER BY id;')
            return jsonify(cur.fetchall()), 200


@app.route('/clients', methods=['GET'])
@require_roles(OIDC.staff_role)
def get_clients():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM clients ORDER BY id;')
            return jsonify(cur.fetchall()), 200


@app.route('/jobs', methods=['GET'])
@require_roles(OIDC.customer_role, OIDC.staff_role)
def get_jobs():
    identity = current_identity()
    client = None
    if OIDC.staff_role not in identity.get('roles', []):
        client = get_active_client_for_identity(identity)
        if client is None:
            return jsonify({'error': 'No active client account matches this identity'}), 403

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT j.*, a.name AS agent_name, c.company_name AS client_name
                FROM jobs j
                LEFT JOIN agents a ON a.id = j.agent_id
                LEFT JOIN clients c ON c.id = j.client_id
            """
            if client is not None:
                cur.execute(
                    query + ' WHERE j.client_id = %s ORDER BY j.created_at DESC;',
                    (client['id'],),
                )
            else:
                cur.execute(query + ' ORDER BY j.created_at DESC;')
            return jsonify(cur.fetchall()), 200


@app.route('/inventory', methods=['GET'])
def get_inventory():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM inventory_items ORDER BY name;')
            return jsonify(cur.fetchall()), 200


@app.route('/assistant/chat', methods=['POST'])
def chat_with_inventory_assistant():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': 'A JSON object with a query is required'}), 400

    query = payload.get('query')
    if not isinstance(query, str) or not query.strip():
        return jsonify({'error': 'query must be a non-empty string'}), 400
    if len(query) > 500:
        return jsonify({'error': 'query must be 500 characters or fewer'}), 400

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM inventory_items ORDER BY name;')
            inventory = cur.fetchall()

    return jsonify(answer_inventory_query(query.strip(), inventory)), 200


@app.route('/jobs', methods=['POST'])
@require_roles(OIDC.customer_role)
def create_job():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': 'A JSON object is required'}), 400
    identity = current_identity()
    client = get_active_client_for_identity(identity)
    if client is None:
        return jsonify({'error': 'No active client account matches this identity'}), 403
    agent_id = payload.get('agent_id')
    task = payload.get('task')
    duration_hours = payload.get('duration_hours', 1)

    if not agent_id or not isinstance(task, str) or not task.strip():
        return jsonify({'error': 'agent_id and a non-empty task are required'}), 400

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO jobs (client_id, agent_id, task, duration_hours, status, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, 'queued', NOW(), NOW())
                    RETURNING *;
                    """,
                    (client['id'], agent_id, task.strip(), duration_hours),
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
@require_roles(OIDC.staff_role)
def seed_demo_data():
    initialize_database()
    return jsonify({'status': 'seeded'}), 200


if __name__ == '__main__':
    initialize_database()
    debug = os.environ.get('FLASK_DEBUG', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    app.run(host='0.0.0.0', port=5000, debug=debug)
