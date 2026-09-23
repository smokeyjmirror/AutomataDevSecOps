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

```bash
cd automata-platform
docker compose up --build
```

Then open:

- Client UI: http://localhost:8000
- Admin UI: http://localhost:8001
- API: http://localhost:5000
- Database: localhost:5432

## Example workflow

1. View agents in the client portal.
2. Submit a task request for an agent.
3. The API stores the request and publishes a Kafka event.
4. The worker processes the event and marks the corresponding job as completed.
5. Admins can watch job status in the dashboard.
