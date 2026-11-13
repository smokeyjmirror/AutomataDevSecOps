# Automata Platform

Automata is a faux intra-galactic commerce and logistics platform for renting AI agents to clients for tasks such as threat research, content drafting, data enrichment, operations assistance, and physics-aware fulfillment coordination across star systems.

## Components

- Client portal: a lightweight front-end for browsing available agents and submitting requests
- Admin dashboard: operations view for clients, jobs, and lifecycle status
- API service: exposes agent and job data through a REST interface
- Worker service: consumes Kafka messages and updates job status
- PostgreSQL database: stores agents, clients, and jobs
- Kafka: event backbone for job orchestration
- Physics-aware fulfillment layer: models inter-planetary route constraints, customs envelopes, and transit risk

## Tech stack

- Python + Flask
- PostgreSQL
- Kafka
- Docker Compose
- Static HTML/JavaScript front ends
- Lean 4 for formal verification of galactic commerce rules, route safety, payment invariants, and fulfillment approvals

## Scientific verification layer

The fictional Automata company includes a Lean-based research suite for validating policies, safety constraints, and task classifications in an intra-galactic commerce environment. In this version of the story, Automata is operating a registry for inter-planetary services, cross-system payments, and fulfillment coordination across star systems.

The Lean examples live in the `lean/` folder and model rules such as: a service contract can be approved only when route risk remains below the maximum tolerable threshold, payment escrow is funded, and fulfillment windows are still valid after the relevant physics constraints are applied. These examples are intentionally lightweight and designed to be easy to extend for more advanced inter-stellar logistics logic.

## Quick start

Create a local environment file and replace all placeholder values, including
the database password, Flask signing key, and local Keycloak admin password:

```bash
cp .env.example .env
```

Generate a Flask signing key with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Paste the generated value into `FLASK_SECRET_KEY` in `.env`. For an existing
`.env`, add the new variables from `.env.example` without replacing your
existing database credentials.

For an existing PostgreSQL volume, changing `POSTGRES_PASSWORD` in `.env` does
not change the password stored in that database. Keep the existing password or
update the database role before changing it.

```bash
cd automata-platform
docker compose up --build
```

Then open:

- Client UI: http://localhost:8000
- Admin UI: http://localhost:8001
- API: http://localhost:5000
- Database: localhost:5432
- Local identity provider: http://localhost:8080

## Local OIDC sign-in

The local setup uses Keycloak as a real OpenID Connect provider; it does not
spoof users or bypass authentication. The app uses the standard authorization
code flow with PKCE, validates the ID token signature, issuer, audience, expiry,
nonce, and role claim, and then creates a short-lived, HTTP-only Flask session.
The Keycloak admin port is bound to loopback and is not exposed on other
interfaces.

The imported `automata` realm creates the `automata-app` client and the
`customer` and `staff` realm roles. After Keycloak starts:

1. Sign in to the local Keycloak admin console at http://localhost:8080/admin
   using `KEYCLOAK_ADMIN_USERNAME` and `KEYCLOAK_ADMIN_PASSWORD` from `.env`.
2. Select the `automata` realm and create a user for a customer. Use an email
   matching an active client in the seeded database (for example
   `ops@apexlabs.example`), mark the email verified, set a local password, and
   assign the `customer` realm role.
3. Create a separate staff user, mark its email verified, set a local password,
   and assign the `staff` realm role.
4. Open either UI and use **Sign in**. Customer users see only jobs belonging
   to the client matching their verified email; staff users can access the
   operations dashboard.

The app's OIDC integration is provider-neutral. `OIDC_ISSUER`,
`OIDC_DISCOVERY_URL`, `OIDC_CLIENT_ID`, claim names, roles, and optional
authorization/token/JWKS endpoint overrides are environment-configurable.
The endpoint overrides let the browser use the host-visible authorization URL
while the API container uses Keycloak's internal Docker-network URLs. For a
different provider, register the callback URL
`http://localhost:5000/auth/callback`, enable authorization code + PKCE
(S256), and configure equivalent roles and verified-email claims.

This is a local development setup, not an externally deployable security
configuration: Keycloak runs in development mode over HTTP, and the session
cookie is not marked `Secure`. Use HTTPS, set `SESSION_COOKIE_SECURE=true`, and
apply deployment-specific secret, proxy, and session-storage controls before
exposing the app beyond this VM.

## Example workflow

1. Sign in as a customer in the client portal and browse agents.
2. Submit a task request; the API derives the client account from the verified
   OIDC email rather than accepting a client ID from the browser.
3. The API stores the request and publishes a Kafka event.
4. The worker processes the event and marks the corresponding job as completed.
5. Customers see their own jobs; staff can watch all jobs in the dashboard.

## Inventory Assistant

The client portal includes a read-only Inventory Assistant backed by demo
inventory seeded by the API and PostgreSQL initialization script. Ask for an
item by name or SKU to see its quantity and reorder point, or ask which items
are low in stock to get suggested reorder quantities. Suggestions are
informational only; the assistant does not change stock or place orders.
