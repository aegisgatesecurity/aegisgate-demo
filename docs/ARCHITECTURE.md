# AegisGate Demo - Architecture

## System Overview

```
                       Internet
                          │
                          ▼
              Cloudflare (DNS-only + DDoS)
                          │
                          ▼
                demo.aegisgatesecurity.io
                          │
                          ▼
            ┌─────────────────────────────┐
            │     Render.com (Free)        │
            │     Docker container         │
            │                             │
            │  ┌──────────────────────┐   │
            │  │  nginx (port 80)     │   │
            │  │  reverse proxy       │   │
            │  └──────┬───────────────┘   │
            │         │                   │
            │   ┌─────┴─────┐             │
            │   │           │             │
            │   ▼           ▼             │
            │ ┌─────┐   ┌─────────┐      │
            │ │8083 │   │ 8080    │      │
            │ │sign │   │ aegisg. │      │
            │ │ up  │   │ platform│      │
            │ └─────┘   └─────────┘      │
            │                            │
            │  /data/                    │
            │  ├─ signups/  (CSV)        │
            │  ├─ seed/     (sample data)│
            │  └─ reset.log               │
            └─────────────────────────────┘
                          │
                          ▼
                http://httpbin.org
                (mock upstream LLM)
```

## Components

### 1. **nginx** (port 80)
- Reverse proxy
- Rate limiting (10 req/s per IP, 2 signups/min per IP)
- SSL termination (via Let's Encrypt at the Render.com edge)
- Injects DEMO MODE banner into every response via `sub_filter`
- Routes:
  - `/` and `/signup/*` → signup server (port 8083)
  - `/platform/*` and `/health` → AegisGate platform (port 8080)

### 2. **AegisGate Platform** (port 8080)
- The actual `aegisgate-platform:v3.3.0-beta.2` binary
- Runs in `--mode=demo` with `--target=http://httpbin.org`
- Uses Developer tier license (read-only in demo)
- Proxies LLM requests to httpbin.org (mock upstream)
- Provides the dashboard at `/admin/` or `/dashboard/`

### 3. **Email Signup Server** (port 8083)
- A small Python HTTP server (no dependencies)
- Serves the signup form at `/`
- Handles POST `/signup/submit` to store emails
- Rate limited to 2 signups/min per IP
- Stores emails in `/data/signups/emails.csv`
- Optionally forwards to a webhook (Mailgun, SendGrid, etc.)

### 4. **Sample Data** (`/opt/aegisgate-demo/seed-data/`)
- `threats.json` — 20 pre-loaded threat scenarios
- `mcp-tools.json` — 5 sample MCP tools
- `compliance-eu-ai-act.json` — pre-run 82-control scan
- `dashboard-metrics.json` — 24h of mock activity
- `playground-prompts.json` — 12 interactive test prompts

### 5. **Daily Reset Cron** (background process)
- Runs every 24 hours
- Wipes runtime state (NOT seed data)
- Re-seeds the demo with fresh data
- Logs to `/data/reset.log`

## Request Flow (Example: User visits demo.aegisgatesecurity.io)

1. **User visits** `https://demo.aegisgatesecurity.io/`
2. **Cloudflare resolves** DNS to Render.com edge
3. **Render.com** terminates SSL, forwards to container
4. **nginx** receives request, rate-limits it
5. **nginx** routes `/` to the signup server
6. **Signup server** returns the signup form
7. **nginx** injects the DEMO MODE banner into the response
8. **User sees**: signup form with DEMO MODE badge in top-right
9. **User submits** email
10. **Signup server** validates, rate-limits, stores email, returns success
11. **User is redirected** to `/dashboard/`
12. **nginx** routes `/dashboard/` to `/platform/`
13. **AegisGate platform** receives request, returns dashboard page
14. **nginx** injects DEMO MODE banner into the response
15. **User sees**: AegisGate dashboard with DEMO MODE badge

## Data Flow

### Email Signup Data
```
User submits email
    │
    ▼
Signup server (port 8083)
    │
    ├─ Validates format (regex)
    ├─ Checks rate limit (in-memory)
    ├─ Stores in /data/signups/emails.csv
    ├─ Optionally POSTs to webhook URL
    │
    ▼
Returns success
```

### Platform Request Data
```
User makes platform request
    │
    ▼
AegisGate platform (port 8080)
    │
    ├─ Validates input
    ├─ Checks against detection patterns
    ├─ If safe: forwards to upstream (httpbin.org)
    ├─ If threat: blocks, logs event
    │
    ▼
Returns response (with optional PII redaction)
```

## File Layout

```
/opt/aegisgate-demo/
├── seed-data/                # Sample data (read-only at runtime)
│   ├── threats.json
│   ├── mcp-tools.json
│   ├── compliance-eu-ai-act.json
│   ├── dashboard-metrics.json
│   └── playground-prompts.json
├── email-signup/             # Signup form + handler
│   ├── index.html
│   └── signup.py
├── scripts/
│   ├── entrypoint.sh         # Container entrypoint
│   ├── demo-banner.css       # Injected banner styles
│   └── demo-banner.js        # Injected banner script
└── nginx/
    └── nginx.conf            # Reverse proxy config

/data/                        # Runtime data (persistent)
├── signups/
│   ├── emails.csv            # Email signups (timestamp, email, hash, IP, UA)
│   └── access.log            # Signup server access log
├── seed/                     # Copy of seed-data/ (for daily reset)
└── reset.log                 # Daily reset events
```

## Ports

| Port | Service | Public? |
|---|---|---|
| 80 | nginx (reverse proxy) | ✅ Yes (only public port) |
| 8080 | AegisGate platform proxy | ❌ Internal only |
| 8081 | AegisGate MCP server | ❌ Internal only |
| 8082 | AegisGate compliance API | ❌ Internal only |
| 8083 | Email signup server | ❌ Internal only |
| 8443 | AegisGate admin dashboard | ❌ Internal only |

Render.com only exposes port 80 (via `port: 8080` in render.yaml — Render auto-detects the port that nginx listens on).

## Why This Architecture?

1. **Single container** — easier to deploy, easier to manage on free tier
2. **nginx in front** — handles rate limiting, SSL, header injection
3. **Mock upstream (httpbin.org)** — no real LLM calls, no API key required
4. **In-memory rate limiting** — no Redis needed
5. **CSV for signups** — easy to export, no database needed
6. **Daily reset** — keeps the demo fresh without manual intervention
7. **Read-only seed data** — cannot be modified by demo users
8. **Separate from platform repo** — changes to the demo don't affect the platform

## Limitations

1. **Free tier sleeps after 15 minutes** — first request after sleep takes ~30s
2. **httpbin.org is rate-limited** — the mock upstream may throttle under heavy load
3. **No real LLM calls** — threat detection is shown but the upstream is mock
4. **No user accounts** — email signup is a soft gate (anyone can sign in as any email)
5. **In-memory rate limit** — doesn't survive container restarts
6. **CSV signup storage** — doesn't scale beyond a few thousand signups

These are acceptable for a demo. For production self-hosting, users would:
- Use the real LLM providers
- Add a real database (PostgreSQL)
- Add proper user accounts
- Add persistent rate limiting (Redis)
- Add real email service integration
