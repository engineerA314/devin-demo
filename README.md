# Devin Superset Incident Autopilot

An event-driven engineering workflow that turns production signals from an
embedded Apache Superset deployment into investigated, tested pull requests
using Devin Cloud.

The first working slice is **Luma**, a mock customer analytics product. It uses
the real `@superset-ui/embedded-sdk` integration and obtains short-lived guest
tokens from a server-side controller. When Superset is not configured, it
renders a polished preview so the product shell remains easy to review.

## Current architecture

```text
Browser (Luma)                       Controller
  GET /api/config ------------------> embedding mode + dashboard identity
  POST /api/superset/guest-token ---> Superset login + guest token exchange
  Superset Embedded SDK ------------> Superset dashboard iframe
```

Superset credentials remain in the controller. They are never included in the
browser bundle or returned to the client.

## Run the preview

No Superset instance or credentials are required:

```bash
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000). The controller health
endpoint is available at [http://localhost:8000/health](http://localhost:8000/health).

## Connect an embedded Superset dashboard

1. Start a Superset instance and enable the `EMBEDDED_SUPERSET` feature flag.
2. In Superset, enable embedding for the selected dashboard and allow
   `http://localhost:3000` as a parent origin.
3. Create a service account that can request guest tokens and view the selected
   dashboard.
4. Copy the environment template and fill in the dashboard identity and service
   account credentials:

```bash
cp .env.example .env
```

```dotenv
SUPERSET_INTERNAL_URL=http://host.docker.internal:8088
SUPERSET_PUBLIC_URL=http://localhost:8088
SUPERSET_DASHBOARD_ID=your-embedded-dashboard-id
SUPERSET_USERNAME=admin
SUPERSET_PASSWORD=your-local-password
```

5. Restart the stack:

```bash
docker compose up --build
```

`SUPERSET_INTERNAL_URL` is used by the controller container.
`SUPERSET_PUBLIC_URL` is used by the browser iframe, so it must be reachable
from the host machine.

## Local development

Web application:

```bash
cd apps/web
npm install
npm run dev
```

Controller:

```bash
cd apps/controller
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Repository roles

- This repository contains the product demo, incident control plane, failure
  scenarios, Devin API integration, reporting, and Docker runtime.
- [`engineerA314/superset`](https://github.com/engineerA314/superset) contains
  the issues and remediation pull requests produced by the workflow.

## Planned workflow

```text
Embedded dashboard failure
  -> observability webhook
  -> incident record and GitHub issue
  -> Devin API session
  -> reproduced failure and code change
  -> pull request and independent validation
  -> human approval
```

## Secrets

`.env` is ignored by Git. Do not commit Superset, GitHub, or Devin credentials.
