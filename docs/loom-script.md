# Five-minute Loom runbook

Target length: **4:35**. Record at 1440p with the browser zoom around 90%.
Keep these tabs ready: Luma dashboard, Incident Autopilot, Devin Automations,
triage session, remediation session, GitHub issue #1, and GitHub PR #2.

## 0:00–0:40 — What: customer impact

**Screen:** Luma customer analytics dashboard.

> This is Luma, a mock SaaS product that serves customer-facing analytics
> through Apache Superset's real Embedded SDK. In this architecture a guest
> token endpoint keeps every embedded dashboard authenticated. If a transient
> outage causes hundreds of clients to refresh together, a fixed retry schedule
> can turn a short dependency failure into repeated traffic spikes and a longer
> customer outage.

**Screen:** Briefly show GitHub issue #1's measured incident summary.

> In the current Superset default branch, failed refreshes retry every ten
> seconds without jitter or backoff. Our deterministic reproduction showed all
> 50 clients arriving in the same one-second bucket for seven consecutive
> waves.

## 0:40–1:25 — How: trigger and architecture

**Screen:** Incident Autopilot, then click **Simulate production incident** only
if a fresh run is desired. For the final recording, the completed incident can
be shown without generating a duplicate issue.

> A real customer would connect Datadog, Better Stack, or another monitor. This
> button sends the same webhook shape: service, severity, error rate, latency,
> affected sessions, monitor threshold, and the proposed explanation. The
> controller persists the incident, then calls a signed native Devin Automation
> webhook. It does not directly tell GitHub what code to change.

**Screen:** README Mermaid diagram or automation provisioning code.

> I split the workflow into two independent agents. The first Devin validates
> the alert and creates an evidence-backed issue. The `devin-ready` label is the
> handoff contract and triggers a second, GitHub-event-driven Automation that
> implements and verifies the fix. Both run in a prebuilt Superset cloud
> environment created through the Devin API.

## 1:25–2:15 — Triage Devin

**Screen:** Triage Devin session, scroll past the alert payload into its work;
then open issue #1.

> The monitor's root cause is treated as a hypothesis. Triage Devin inspected
> the current default branch, created a fake-timer reproduction, and measured
> 350 failed attempts in seven synchronized waves. Only after confirming the
> repository owned the failure did it create this issue with customer impact,
> exact evidence, source locations, and acceptance criteria. It did not modify
> production code.

## 2:15–3:15 — Remediation Devin

**Screen:** Remediation session timeline and its changes, then PR #2.

> Applying `devin-ready` emitted a GitHub issue event and automatically started
> a fresh remediation session. Devin independently reproduced the behavior,
> added equal-jitter exponential backoff with a five-minute cap, reset the
> backoff after recovery, and preserved unmount cancellation. It added fleet,
> backoff, reset, cancellation, and helper tests, updated the embedding docs,
> pushed a branch, commented on the issue, and opened this PR.

**Screen:** PR test section.

> The agent ran 23 SDK tests and the production build. I also checked out the
> exact PR commit in a clean worktree and independently reran `npm ci`, all 23
> tests, and the TypeScript, Babel, and Webpack build. Merge remains a human
> approval gate.

## 3:15–4:05 — Observability and engineering depth

**Screen:** Completed Incident Autopilot dashboard.

> An engineering leader can see whether the system is working without reading
> agent transcripts: alert accepted, zero active workers, two completed Devins,
> one pull request, no failed runs, and a 100 percent success signal. The
> timeline links directly to both sessions, the issue, and the PR. The backend
> joins a durable SQLite incident log with live Devin Automation and session
> APIs plus GitHub artifacts every five seconds.

**Screen:** `scripts/provision_devin.py`, briefly show limits and prompts.

> The operating controls are also code: per-session ACU budgets, hourly rate
> limits, concurrency and queue caps, explicit triage and remediation scopes,
> and no autonomous merge. The environment and both native Automations are
> reproducible from the public Docker project.

## 4:05–4:35 — Why Devin, and when to extend

**Screen:** Automation dashboard with the two sessions or the architecture.

> A local coding assistant can fix one issue after an engineer opens a laptop.
> This system adds unattended engineering capacity: an alert starts work in a
> consistent cloud environment, multiple sessions can run concurrently, and
> reviewable outputs continue to arrive while the on-call engineer is handling
> the incident or offline. At a customer, I would next connect the real monitor,
> add ownership and severity policies, measure time-to-validated-issue and
> time-to-PR, gate high-risk repositories more tightly, and use acceptance and
> rollback rates to decide where autonomy should expand.
