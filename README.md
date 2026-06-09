# AegisGate Demo Environment

> **Live, interactive demo of the [AegisGate Security Platform](https://github.com/aegisgatesecurity/aegisgate-platform)**
>
> **Status:** 🚧 In development (2026-06-09)
> **Live URL:** https://demo.aegisgatesecurity.io (after deploy)
> **Hosting:** Render.com free tier
> **License:** Apache 2.0

This repository contains the **demo environment** for AegisGate — a separate, isolated deployment that:

- Runs the [v3.3.0-beta.2 platform binary](https://github.com/aegisgatesecurity/aegisgate-platform/releases/tag/v3.3.0-beta.2) in `--mode=demo`
- Uses **synthetic, non-production data** (sample threats, sample MCP tools, sample compliance scans)
- Has a **prominent DEMO MODE badge** so visitors know it's not production
- Requires **email signup** (we use this to build a marketing list — no spam, just product updates)
- Resets state **every 24 hours** to keep the demo fresh
- Has **rate limits** to prevent abuse
- Has a **read-only admin dashboard** (no real configuration changes can be made)

## 🆚 How is this different from the platform repo?

| Concern | Platform repo (`aegisgate-platform`) | This repo (`aegisgate-demo`) |
|---|---|---|
| **Purpose** | Production code | Demo deployment configuration |
| **Audience** | Developers who self-host AegisGate | Prospects evaluating AegisGate |
| **Container image** | Source of truth — `ghcr.io/aegisgatesecurity/aegisgate-platform:v3.3.0-beta.2` | Consumes the image, doesn't build it |
| **Custom Dockerfile** | `Dockerfile` (in platform repo) | `Dockerfile.demo` (this repo) — adds demo mode |
| **Custom binary flag** | Source of `--mode=demo` flag (in main.go) | Used in compose file to start demo |
| **Sample data** | N/A | `seed-data/` directory with realistic examples |
| **Email signup** | N/A | `email-signup/` directory with form + storage |
| **Render config** | N/A | `render.yaml` (Blueprint) |
| **Documentation** | User-facing product docs | This README + Render.com setup guide |

The two repos are **completely independent**:
- A change to the platform code doesn't affect the demo
- A change to the demo config doesn't affect the platform
- Each has its own CI/CD, its own issues, its own release cadence

## 📁 Repository Structure

```
aegisgate-demo/
├── README.md                       # This file
├── LICENSE                         # Apache 2.0
├── .gitignore                      # Git ignore patterns
├── Dockerfile.demo                 # Custom Docker build for demo mode
├── docker-compose.demo.yml         # Local testing (optional)
├── render.yaml                     # Render.com Blueprint (auto-deploy)
├── seed-data/                      # Sample data for the demo
│   ├── threats.json                # 15-20 pre-loaded threat examples
│   ├── mcp-tools.json              # 3-5 sample MCP servers
│   ├── compliance-eu-ai-act.json   # Pre-run EU AI Act scan (82 controls)
│   ├── dashboard-metrics.json      # 24h of mock activity
│   └── playground-prompts.json     # Interactive test inputs
├── email-signup/                   # Email gate
│   ├── index.html                  # Signup form page
│   ├── signup.html                 # Form handler
│   ├── store.js                    # Simple JS-based storage
│   └── verify.html                 # Email verification page
├── scripts/
│   ├── seed-demo.sh                # Initialize demo data
│   ├── reset-demo.sh               # Reset to clean state
│   └── send-welcome-email.sh       # (optional) email new signups
├── nginx/                          # Reverse proxy config
│   ├── nginx.conf
│   └── cloudflare.conf
└── docs/
    ├── ARCHITECTURE.md             # How the demo is set up
    ├── SECURITY.md                 # Safety/sandboxing approach
    └── RUNBOOK.md                  # How to operate the demo
```

## 🚀 Quick Start (Local Development)

```bash
# 1. Clone this repo
git clone https://github.com/aegisgatesecurity/aegisgate-demo.git
cd aegisgate-demo

# 2. Pull the platform image
docker pull ghcr.io/aegisgatesecurity/aegisgate-platform:v3.3.0-beta.2

# 3. Start the demo
docker compose -f docker-compose.demo.yml up -d

# 4. Visit the demo
open http://localhost:8080    # AegisGate proxy
open http://localhost:8443    # Admin dashboard (read-only in demo)
```

## 🌐 Production Deployment (Render.com)

This repo is configured for **Render.com Blueprint** deployment:

1. **Sign in to Render.com** with GitHub
2. **New + → Blueprint** → select this repo (`aegisgate-demo`)
3. Render auto-detects `render.yaml` and provisions the services
4. Add custom domain: `demo.aegisgatesecurity.io`
5. Render provisions Let's Encrypt SSL automatically
6. **Email webhook**: configure `RENDER_EMAIL_WEBHOOK_URL` env var to forward signups to your email service (Mailgun, SendGrid, etc.)

See [`docs/RUNBOOK.md`](docs/RUNBOOK.md) for the full deployment guide.

## 🛡️ Safety & Sandboxing

The demo is **publicly accessible**, so we take precautions:

1. **No real data** — only synthetic sample data
2. **No real API keys** — AegisGate is run with `--target=httpbin.org` (mock upstream) so it doesn't contact real LLM providers
3. **Read-only admin dashboard** — UI is restricted from making real changes
4. **Rate limits** — Cloudflare in front, plus AegisGate's built-in rate limiting
5. **Daily reset** — State is wiped every 24 hours
6. **No PII collection** — Email is the only field we ask for
7. **"This is a demo" banner** — Prominent in the UI

## 🔒 Security Disclosure

Found a vulnerability in the demo? Please email **security@aegisgatesecurity.io** (PGP key on https://aegisgatesecurity.io/security). We respond to demo-related security issues within 48 hours.

## 📊 Sample Data (What Visitors See)

The demo comes pre-loaded with:

| Type | Count | Description |
|---|---|---|
| **Threat scenarios** | 15-20 | Pre-loaded examples of prompt injection, PII exposure, jailbreak attempts, etc. |
| **MCP tools** | 3-5 | Sample MCP servers (filesystem, web search, database query) |
| **Compliance scan** | 82 controls | Pre-run EU AI Act scan with realistic statuses (mix of ✅, ⚠️, ❌) |
| **Dashboard metrics** | 24h of data | Mock activity charts, request rates, threat detection rates |
| **Playground prompts** | 10-15 | Interactive test inputs visitors can try |

## 🛠️ Development

To modify the demo:

1. Edit `seed-data/*.json` to add/change sample data
2. Edit `Dockerfile.demo` if you need different base image layers
3. Edit `docker-compose.demo.yml` for port mappings, env vars, etc.
4. Edit `render.yaml` for Render.com-specific config
5. Commit and push — Render.com auto-deploys

## 🤝 Contributing

We welcome PRs that improve the demo experience! Some ideas:
- Add more sample threat scenarios
- Improve the email signup UX
- Add more dashboard visualizations
- Improve the "Try it" playground

Please open an issue first to discuss larger changes.

## 📄 License

This repository is licensed under **Apache License 2.0** — see [LICENSE](LICENSE) for details.

The AegisGate platform binary it deploys is also Apache 2.0.

## 📞 Contact

- **General questions**: hello@aegisgatesecurity.io
- **Security issues**: security@aegisgatesecurity.io
- **Sales**: sales@aegisgatesecurity.io
- **GitHub**: https://github.com/aegisgatesecurity
- **Website**: https://aegisgatesecurity.io

---

*This demo is provided as-is for evaluation purposes. It is not a production service. See the prominent DEMO MODE badge in the UI for confirmation.*
