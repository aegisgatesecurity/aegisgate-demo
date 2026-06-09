# AegisGate Demo - Security & Sandboxing

## Threat Model

The AegisGate demo is **publicly accessible** at `https://demo.aegisgatesecurity.io`. As such, it is a target for:

- **Bots / scrapers** — trying to harvest email addresses
- **Abusers** — trying to use the demo for malicious purposes (e.g., testing attacks against the LLM upstream)
- **Spammers** — trying to use the signup form to send spam
- **Curious researchers** — testing AegisGate's detection capabilities
- **Hostile actors** — probing for vulnerabilities in the demo infrastructure

This document describes the **safety measures** we take to mitigate these risks.

## Safety Layers

### Layer 1: Public-Facing Network (Cloudflare + Render.com)

| Control | Description |
|---|---|
| **Cloudflare DNS-only mode** | DNS resolution goes through Cloudflare, but traffic is NOT proxied. DDoS protection is limited but better than nothing. |
| **Render.com edge** | Render.com terminates SSL and provides basic DDoS protection at the edge. |
| **Let's Encrypt SSL** | All traffic is HTTPS. No plaintext. |
| **HTTP → HTTPS redirect** | Render.com auto-redirects HTTP to HTTPS. |

### Layer 2: nginx (reverse proxy)

| Control | Description |
|---|---|
| **Rate limit (general)** | 10 requests/second per IP, burst 20. |
| **Rate limit (signup)** | 2 signups/minute per IP. |
| **Security headers** | X-Frame-Options, X-Content-Type-Options, Referrer-Policy, X-XSS-Protection. |
| **sub_filter** | Injects DEMO MODE banner into every page (so users always know it's a demo). |
| **No directory listing** | nginx is configured to not serve directory listings. |

### Layer 3: Email Signup Server (Python)

| Control | Description |
|---|---|
| **Email format validation** | Regex check on submitted emails. |
| **Per-email rate limit** | 5 signups per email per hour (in-memory). |
| **Per-IP rate limit** | 2 signups per IP per minute (enforced by nginx). |
| **CSV storage** | Emails stored in CSV (not in a database that could be compromised). |
| **Optional webhook** | Signups can be forwarded to Mailgun/SendGrid/Zapier (configured via env var). |
| **No email sending from demo** | The demo doesn't send emails (except via the optional webhook). |
| **Hash storage** | Email is SHA-256 hashed before logging, so PII is not exposed in logs. |

### Layer 4: AegisGate Platform

| Control | Description |
|---|---|
| **Mock upstream (httpbin.org)** | All LLM-like requests go to httpbin.org (a mock HTTP service). **No real LLM provider is contacted.** |
| **No API keys in environment** | The platform runs in demo mode without any real LLM API keys. |
| **Rate limits** | 100 requests/hour per visitor (configurable). |
| **Threat detection** | All the same detection capabilities as production, just pointed at a mock upstream. |
| **No real data** | All sample data is synthetic. |
| **Daily reset** | State is wiped every 24 hours, so no long-term data accumulation. |

### Layer 5: Container Isolation

| Control | Description |
|---|---|
| **Read-only seed data** | `/opt/aegisgate-demo/seed-data/` is mounted read-only. |
| **Separate data volume** | `/data/` is on a separate volume, can be wiped without affecting seed data. |
| **No root login** | Container runs as non-root user. |
| **Resource limits** | Docker `deploy.resources` limits CPU and memory. |
| **Single process per service** | Each component (platform, signup server, nginx) runs in its own process. |

## What's NOT in Scope

The following are **not** protected by the demo and would need additional measures for production:

1. **Real LLM provider integration** — Production would use OpenAI, Anthropic, etc. with real API keys.
2. **Real user data** — Production would store real customer data, requiring encryption at rest, GDPR compliance, etc.
3. **Multi-tenancy** — Production would isolate different customers' data.
4. **Persistent storage** — Production would use a real database, not CSV.
5. **Audit logging** — Production would log to a SIEM, not a local file.
6. **Backup/recovery** — Production would have regular backups, not just daily resets.
7. **WAF** — Production would use a WAF (e.g., Cloudflare WAF, AWS WAF) in front.
8. **DDoS protection** — Production would use Cloudflare's full proxy mode, not DNS-only.

## What Attackers Can Do

Even with all the safety measures, an attacker CAN:

1. **Submit any email** they want (limited by rate limits)
2. **Make 100 requests/hour** to the platform (limited)
3. **Try all the sample threats** in the playground (intentional — that's the point of the demo)
4. **Read the seed data** (intentional — public information)
5. **View the source code** of the demo UI (intentional — open source)

## What Attackers CANNOT Do

1. **Send real LLM requests** to OpenAI/Anthropic/etc. (mock upstream only)
2. **Access the admin dashboard** with write permissions (read-only in demo)
3. **Access other users' data** (no multi-tenancy, no persistent data)
4. **Persist data** beyond the daily reset (everything wipes)
5. **Exfiltrate real PII** (no real PII in the system)
6. **Use the demo for production** (clearly marked as DEMO MODE)

## Reporting Security Issues

If you find a security issue in the demo, please report it to **security@aegisgatesecurity.io** (PGP key on https://aegisgatesecurity.io/security). We respond to demo-related security issues within 48 hours.

For security issues in the **AegisGate platform itself**, see https://github.com/aegisgatesecurity/aegisgate-platform/security/policy

## Why This Is Good Enough

The demo's security model is designed for the threat model:
- The demo is **not** a production environment
- All data is **synthetic**
- All requests are **rate-limited**
- The platform is **clearly marked** as DEMO MODE
- The infrastructure is **isolated** from production

This is a reasonable balance between "useful demo" and "not a security liability". A determined attacker could do some damage, but:
- No real customer data is at risk
- No real LLM costs can be incurred
- No real users are affected (everyone using the demo knows it's a demo)
- The damage is contained to the demo environment itself

If we wanted to make it more secure, we could:
- Add Cloudflare WAF in proxy mode (full DDoS protection)
- Add Cloudflare Turnstile to the signup form (anti-bot)
- Add a real WAF (AWS WAF, ModSecurity)
- Use a private network for the platform (not internet-accessible)
- Require email verification before granting access

But these would add friction to the demo experience. For a public demo, the current model is a good balance.

## Compliance

The demo is designed to be **safe by default** for:

- **GDPR**: No real personal data is processed. Email signup is the only PII collected, and users can request deletion by emailing privacy@aegisgatesecurity.io.
- **CCPA**: Same as GDPR — no real personal data, email can be deleted on request.
- **EU AI Act**: The demo **shows** EU AI Act compliance, but the demo itself is not a high-risk AI system (it's a test environment, not a deployed system).

For the AegisGate platform's compliance posture, see the production documentation at https://aegisgatesecurity.io/docs/compliance/.
