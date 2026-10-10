# ClosureIQ

Hack Midwest 2026, Kansas City (Oct 10-11)

## Team

| Role | Full name | School email | GitHub |
|---|---|---|---|
| Team lead | Sai Samanth Kumar Pendyala | sxp90460@ucmo.edu | [samkumar266](https://github.com/samkumar266) |
| Member | Suraj Sirikonda | sxs98450@ucmo.edu | [surajreddy0011](https://github.com/surajreddy0011) |
| Member | Nooka Badrinath (confirm spelling) | bxn23430@ucmo.edu | [Badrinathnooka](https://github.com/Badrinathnooka) |
| Member | Kavya (full name) | kxk10070@ucmo.edu | (GitHub username, added later) |

## What does our app do?

ClosureIQ helps facility managers decide whether to delay arrival, dismiss early, telework or close during severe weather, and notifies the right employees. It pulls live National Weather Service alerts and forecasts plus a USGS river gauge, applies a sourced threshold table, and recommends one of five postures with the inputs, timestamps, threshold crossed, confidence and what would change the call. A manager approves, ClosureIQ builds the notification package (who, why, message, channel), simulates delivery and escalation, and keeps an append-only decision record that can be replayed to the identical result. A Strands agent explains the recommendation and answers what-if questions but cannot decide or send anything.

## Which challenges are we building for? (select all that apply)

See https://hackmidwest.com/#prizes for details.

- [ ] Flex: Best FinTech App
- [x] AWS: Best Use of Strands Agents SDK
- [x] Akamai Cloud AI Challenge
- [ ] DevRev Challenge
- [x] USDA AI Challenge

## Tech stack

- Frontend: React, Vite, TypeScript, Tailwind
- Backend: Python, FastAPI, SQLite, APScheduler
- AI / data: Strands Agents SDK; National Weather Service API, USGS water services, NOAA NWPS
- Hosting: Akamai Cloud

## Tools and AI assistance

We use third-party frameworks and libraries only. Team members use different AI coding assistants (including Claude) to help write code during the event. All code in this repo was written during the competition.

## How to run it

_Fill in once there is something to run. See AGENTS.md for the current commands._
