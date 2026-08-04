# 📧 Demo Site Email Setup — Direct Resend Integration

**Quick setup guide for email signup notifications**

---

## 🎯 What Changed

**Before:** Signup → Pipedream (quota limits) → Resend → Email  
**Now:** Signup → Resend API → Email ✅

**Benefits:**
- ✅ No Pipedream quota limits
- ✅ Simpler architecture (one service, not two)
- ✅ Faster delivery (no middleman)
- ✅ More reliable (fewer failure points)

---

## 🔧 Setup Steps (5 minutes)

### Step 1: Get Your Resend API Key

1. Go to https://resend.com/api-keys
2. Click **"Create API Key"** (or copy existing)
3. Copy the key (starts with `re_`)

---

### Step 2: Add to Render.com Dashboard

1. Go to https://dashboard.render.com
2. Select your **aegisgate-demo** service
3. Click **"Environment"** tab
4. Click **"Add Environment Variable"** three times:

| Key | Value | Notes |
|-----|-------|-------|
| `AEGISGATE_RESEND_API_KEY` | `re_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` | Your API key |
| `AEGISGATE_RESEND_TO_EMAIL` | `security@aegisgatesecurity.io` | Where notifications go |
| `AEGISGATE_RESEND_FROM_EMAIL` | `onboarding@resend.dev` | Test mode (works now) |

5. Click **"Save Changes"**
6. Wait for auto-redeployment (~1-2 min)

---

### Step 3: Test It

1. Go to your demo site (Render URL)
2. Fill out the signup form with a test email
3. Submit
4. Check your email at `security@aegisgatesecurity.io`

**Expected result:** You receive an email with subject:  
`New Demo Signup: test@example.com`

---

## 📋 Email Format

When someone signs up, you'll receive an email like this:

```html
<h2>New Demo Site Signup!</h2>
<p><strong>Email:</strong> user@example.com</p>
<p><strong>IP Address:</strong> 192.168.1.1</p>
<p><strong>Time:</strong> 2026-08-04T12:30:00Z</p>
<p><strong>Source:</strong> aegisgate-demo</p>
<p><strong>User Agent:</strong> Mozilla/5.0...</p>
```

---

## 🚀 Production Mode (Optional)

Once you verify your domain in Resend:

1. Go to https://resend.com/domains
2. Add `aegisgatesecurity.io`
3. Add the DNS records Resend provides
4. Update Render.com env var:
   - `AEGISGATE_RESEND_FROM_EMAIL` = `notifications@aegisgatesecurity.io`

**Test mode** (`onboarding@resend.dev`) works immediately without domain verification.

---

## 🔍 Troubleshooting

### No email received?

1. **Check Render logs:**
   ```bash
   # In Render dashboard → Logs tab
   # Look for: "Resend email sent successfully"
   ```

2. **Check Resend dashboard:**
   - Go to https://resend.com/emails
   - Look for recent sends
   - Check for errors/bounces

3. **Verify env vars are set:**
   ```bash
   # SSH into Render container (if you have access)
   echo $AEGISGATE_RESEND_API_KEY
   ```

### Email shows "undefined" values?

This was the old Pipedream issue. With direct Resend integration, this shouldn't happen. If it does:

1. Check Render logs for errors
2. Verify the signup form is submitting correctly
3. Check browser console for JavaScript errors

---

## 📚 Architecture

```
┌─────────────────┐
│  Demo Site      │
│  Signup Form    │
└────────┬────────┘
         │ POST /signup/submit
         ▼
┌─────────────────┐
│  signup.py      │
│  (Python HTTP)  │
└────────┬────────┘
         │ Calls Resend API
         │ (if API key configured)
         ▼
┌─────────────────┐
│  Resend.com     │
│  Email API      │
└────────┬────────┘
         │ Sends email
         ▼
┌─────────────────┐
│  Your Inbox     │
│  security@...   │
└─────────────────┘
```

**Legacy fallback:** If `AEGISGATE_RESEND_API_KEY` is not set, the code falls back to the old `EMAIL_WEBHOOK_URL` method (for backwards compatibility).

---

## ✅ Verification Checklist

- [ ] Resend API key added to Render.com
- [ ] `AEGISGATE_RESEND_TO_EMAIL` set
- [ ] `AEGISGATE_RESEND_FROM_EMAIL` set (test mode OK)
- [ ] Render.com redeployed successfully
- [ ] Test signup submitted
- [ ] Email received at `security@aegisgatesecurity.io`
- [ ] Render logs show "Resend email sent successfully"

---

**Questions?** See `/EMAIL-BUG-FIX.md` for full root cause analysis.
