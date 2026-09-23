CREATE TABLE IF NOT EXISTS agents (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    kind VARCHAR(50) NOT NULL,
    capability TEXT NOT NULL,
    rate_per_hour NUMERIC(10,2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'available'
);

CREATE TABLE IF NOT EXISTS clients (
    id SERIAL PRIMARY KEY,
    company_name VARCHAR(150) NOT NULL,
    contact_email VARCHAR(150) NOT NULL UNIQUE,
    account_status VARCHAR(20) NOT NULL DEFAULT 'active'
);

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

INSERT INTO agents (name, kind, capability, rate_per_hour, status)
VALUES
    ('Atlas', 'Research Agent', 'Threat intelligence and reconnaissance', 85.00, 'available'),
    ('Mira', 'Ops Agent', 'Infrastructure hardening and deployment support', 95.00, 'available'),
    ('Nova', 'Content Agent', 'Policy summaries and internal documentation', 60.00, 'available')
ON CONFLICT (name) DO NOTHING;

INSERT INTO clients (company_name, contact_email, account_status)
VALUES
    ('Apex Labs', 'ops@apexlabs.example', 'active'),
    ('Northstar Secure', 'security@northstar.example', 'active'),
    ('Blue Harbor', 'dm@blueharbor.example', 'active')
ON CONFLICT (contact_email) DO NOTHING;
