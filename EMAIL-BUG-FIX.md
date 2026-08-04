# 📧 EMAIL NOTIFICATION BUG — ROOT CAUSE & FIX

**Date:** 2026-08-03  
**Status:** ✅ ROOT CAUSE IDENTIFIED  
**Priority:** HIGH (P2)

---

## 🔍 PROBLEM STATEMENT

The demo site email registration form has **NEVER** sent a notification email since initial deployment. Users can sign up, but no webhook notification is sent to the configured email service.

---

## 🎯 ROOT CAUSE

### Primary Issue: `EMAIL_WEBHOOK_URL` Not Set in Render.com

**Location:** `render.yaml` lines 57-59

```yaml
- key: EMAIL_WEBHOOK_URL
  sync: false  # Set this in the Render dashboard (not committed)
```

The `sync: false` directive means this environment variable is **NOT deployed via the Render Blueprint**. It must be set **manually in the Render.com dashboard**.

**Why this matters:**
- The `signup.py` server checks `WEBHOOK_URL = os.environ.get("EMAIL_WEBHOOK_URL", "")` (line 34)
- The `send_webhook()` function returns early if `WEBHOOK_URL` is empty (line 147)
- **Result:** Signups are stored locally in CSV, but **no notification is ever sent**

### Secondary Issue: No Documentation for Webhook Setup

The `.env.example` file shows:
```bash
# Optional: leave blank to only store locally
EMAIL_WEBHOOK_URL=
```

This makes it seem optional, but for production use, it's **required** to receive signup notifications.

---

## ✅ FIX STEPS

### Step 1: Set EMAIL_WEBHOOK_URL in Render.com Dashboard

1. **Log in to Render.com**
2. **Navigate to:** `aegisgate-demo` service → **Environment** tab
3. **Add new environment variable:**
   - **Key:** `EMAIL_WEBHOOK_URL`
   - **Value:** Your webhook endpoint URL (see options below)
4. **Save changes** — Render will auto-redeploy

### Step 2: Choose a Webhook Service

You have several options for receiving signup notifications:

#### Option A: Webhook.site (Free, Testing)
```
https://webhook.site/your-unique-id
```
- ✅ Instant setup
- ✅ View payloads in browser
- ❌ Not suitable for production (URLs expire)

#### Option B: Mailgun (Production)
```
https://api.mailgun.net/v3/yourdomain.com/messages
```
- Set `EMAIL_WEBHOOK_URL` to Mailgun's API endpoint
- Configure Mailgun to send emails on webhook receipt
- Requires Mailgun account and domain verification

#### Option C: SendGrid (Production)
```
https://api.sendgrid.com/v3/mail/send
```
- Similar to Mailgun
- Requires SendGrid account and API key

#### Option D: Zapier/Make (No-Code)
```
https://hooks.zapier.com/hooks/catch/your-webhook-id
```
- Connects to 5000+ apps (Slack, Google Sheets, CRM, etc.)
- Easy to set up automations

#### Option E: Custom Endpoint
```
https://your-server.com/api/aegisgate-signup
```
- Build your own webhook receiver
- Full control over processing

### Step 3: Test the Fix

After setting the environment variable:

```bash
# 1. Wait for Render to redeploy (check service logs)
# 2. Visit https://demo.aegisgatesecurity.io/
# 3. Fill out the signup form with a test email
# 4. Submit the form
# 5. Check your webhook service for the POST request

# Expected payload:
{
  "email": "test@example.com",
  "ip_address": "192.168.1.1",
  "user_agent": "Mozilla/5.0...",
  "source": "aegisgate-demo",
  "timestamp": "2026-08-03T21:00:00Z"
}
```

### Step 4: Verify in Render Logs

Check the service logs in Render dashboard:

```
# Look for these log messages:
"Signup stored: <hash> (from <ip>)"
"Webhook sent: HTTP 200"  # ← This confirms success
```

If you see `"Webhook failed: ..."` instead, check:
- Webhook URL is correct
- Webhook service is accessible
- No firewall blocking outbound requests from Render

---

## 📝 ADDITIONAL RECOMMENDATIONS

### 1. Update .env.example to Emphasize Production Requirement

**Current:**
```bash
# Optional: leave blank to only store locally
EMAIL_WEBHOOK_URL=
```

**Recommended:**
```bash
# REQUIRED for production: Set to your webhook endpoint
# Options:
#   - Webhook.site (testing): https://webhook.site/your-id
#   - Mailgun: https://api.mailgun.net/v3/yourdomain.com/messages
#   - SendGrid: https://api.sendgrid.com/v3/mail/send
#   - Zapier: https://hooks.zapier.com/hooks/catch/your-id
#
# Leave blank for local dev only (signups stored locally, no notifications)
EMAIL_WEBHOOK_URL=
```

### 2. Add Render Dashboard Setup Instructions to README

Add a new section to `README.md`:

```markdown
## 📧 Email Signup Configuration

To receive email signup notifications:

1. Go to Render.com → aegisgate-demo service → Environment tab
2. Add environment variable: `EMAIL_WEBHOOK_URL`
3. Set value to your webhook endpoint (Mailgun, SendGrid, Zapier, etc.)
4. Save — Render will auto-redeploy

For testing, use https://webhook.site to get a temporary webhook URL.
For production, configure Mailgun, SendGrid, or your own endpoint.
```

### 3. Add Webhook Health Check

Consider adding a `/health/webhook` endpoint to `signup.py` that:
- Tests connectivity to `WEBHOOK_URL`
- Returns status in admin dashboard
- Alerts if webhook has been failing

---

## 🔧 DEBUGGING COMMANDS

### Check if EMAIL_WEBHOOK_URL is set (via admin endpoint)

```bash
curl -H "X-Admin-Token: YOUR_ADMIN_TOKEN" \
  https://demo.aegisgatesecurity.io/admin/status | jq '.signups'
```

### Test webhook manually

```bash
curl -X POST https://your-webhook-url.com/test \
  -H "Content-Type: application/json" \
  -d '{"test": true, "source": "aegisgate-demo-test"}'
```

### Check Render logs for webhook attempts

```bash
# In Render dashboard → Logs → search for:
"Webhook"
```

---

## 📊 IMPACT

**Before Fix:**
- ❌ No email notifications sent
- ❌ Signups only stored in ephemeral CSV (lost on container restart)
- ❌ No way to build marketing list or follow up with prospects

**After Fix:**
- ✅ Real-time signup notifications
- ✅ Can integrate with email marketing platforms
- ✅ Can build prospect database for sales follow-up

---

## 🎯 VERIFICATION CHECKLIST

- [ ] `EMAIL_WEBHOOK_URL` set in Render dashboard
- [ ] Webhook endpoint is accessible (test with curl)
- [ ] Test signup submitted successfully
- [ ] Webhook received the POST request
- [ ] Render logs show `"Webhook sent: HTTP 200"`
- [ ] Documentation updated (`.env.example`, `README.md`)
- [ ] Team notified of fix

---

## 📚 RELATED FILES

- `render.yaml` — Render Blueprint config (line 57-59)
- `.env.example` — Environment variable template (line 29-30)
- `email-signup/signup.py` — Signup server (line 34, 145-163)
- `scripts/entrypoint.sh` — Container startup (line 157-172)
- `nginx/nginx.conf` — Request routing (line 95-100)

---

*Bug identified: 2026-08-03 21:02 UTC*  
*Root cause: EMAIL_WEBHOOK_URL not set in Render.com dashboard*  
*Fix: Set environment variable in Render dashboard + update documentation*
