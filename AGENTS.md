# Project: ClosureIQ

ClosureIQ helps facility managers decide whether to delay, dismiss, telework or close during severe weather, and notifies the right people, by turning live National Weather Service data into an explainable, approvable and recorded recommendation.

Built at Hack Midwest 2026 for the USDA "Closure Call" challenge (also entering the AWS Strands Agents SDK and Akamai Cloud challenges). Read this file before writing any code. Every AI assistant on this team (Claude, Cursor, Copilot, ChatGPT, Gemini, others) follows the same rules, so the code stays consistent.

Architecture: docs/architecture.md (export of the ClosureIQ architecture doc). Task list: Linear, team HAC.

## Demo flow (the only thing that must work)

1. Watchlist shows three facility locations, the one under a real NWS alert on top.
2. Open it: live recommendation (one of five postures) with each input's source and timestamp, the threshold crossed and by how much, confidence, what would change it, and a paste-ready rationale.
3. Ask the Strands agent a what-if; the answer is marked HYPOTHETICAL.
4. Approver approves; the notification package shows who is in or out and why, the drafted messages and channel routing.
5. Delivery tracker: email is real, other channels simulated; the simulated clock fast-forwards an escalation.
6. Decision record: raw evidence, approval, package, deliveries; Replay shows the identical result.

The pitch is 3 minutes of the live app only. No slides. Judges score: usefulness/impact, originality, and whether it is a real working MVP. Code quality is not judged, so working beats pretty.

## Stack

- Frontend: React + Vite + TypeScript + Tailwind in /frontend
- Backend: Python 3.11+, FastAPI, SQLite (append-only), APScheduler in /api
- AI / data: Strands Agents SDK in /ai (model: Akamai-hosted inference or Bedrock, chosen by env var)
- Mock data and recorded real payloads: /mocks
- API contract: docs/contract.md (match its shapes exactly)
- Deploy: Akamai Cloud (Linode) VM

## Folder ownership (do not edit other folders without asking)

- /frontend: Kavya
- /api/ingest, /api/store, /api/app (routers and wiring): Badri , extended by Samanth
- /api/engine and /ai (Strands agent): Samanth
- /api/notify, /docs, /mocks, deploy scripts and Akamai Cloud: Suraj, extended by Kavya
- /api/clock.py: created by Badri, extended by Kavya

## Hackathon rules (these apply to every AI assistant too)

- Use only third-party frameworks and libraries. Never paste in code, designs or tests from earlier projects.
- This repo is private and the organizers can see it. Never commit secrets: keys go in `.env` (git-ignored); add variable names to `.env.example`.
- Deadline is Sunday 8:00 AM. After that, no commits at all (no features, no bug fixes).
- One project per team.

## Rules for AI assistants

- Read docs/contract.md before writing any API or fetch code. Match its shapes exactly.
- Only edit files inside the folder for the current task.
- Do not add new dependencies without saying so in the PR description.
- Prefer simple, working code over abstractions. This is a 24-hour hackathon.
- Never hard-code secrets; read them from environment variables.
- The policy engine is a pure function: no clock, no network, no randomness inside /api/engine.
- The agent has no write tools: it never approves, sends or edits anything.
- Nothing defaults to "normal": a missing or stale source lowers confidence and says so.
- Keep functions small and name things clearly so teammates' AIs can follow the code.
- Commit every time something works. Small commits make rollback easy.
- Ask for a plan before writing code for anything bigger than one file.

## Commands (confirm and update when each skeleton lands)

- Frontend: `cd frontend && npm install && npm run dev`
- Backend: `uvicorn api.main:app --reload` (api/app/main.py is the old what-if/chat-only app; do not deploy it)
- Tests / lint: `pytest`
