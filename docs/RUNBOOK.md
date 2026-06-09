# AegisGate Demo - Operations Runbook

This is a practical guide for operating the AegisGate demo. Read this before making changes or troubleshooting.

## Deployment

### First-time setup (Render.com)

1. **Sign in to Render.com** with GitHub: https://dashboard.render.com/
2. **Create a new Blueprint**:
   - Click "New +" → "Blueprint"
   - Connect the `aegisgatesecurity/aegisgate-demo` repo
   - Render auto-detects `render.yaml` and provisions the service
3. **Configure environment variables** in the Render dashboard:
   - `EMAIL_WEBHOOK_URL` (optional): URL to forward signups to (Mailgun, SendGrid, Zapier, etc.)
   - `CF_TURNSTILE_SITE_KEY` (optional): Cloudflare Turnstile site key
   - `CF_TURNSTILE_SECRET_KEY` (optional): Cloudflare Turnstile secret
4. **Add the custom domain**: `demo.aegisgatesecurity.io`
   - Render auto-provisions a Let's Encrypt certificate
5. **Wait for first deploy** (~5-10 minutes for the Docker build)

### Subsequent deploys

Every push to the `main` branch of `aegisgatesecurity/aegisgate-demo` triggers an auto-deploy. Render builds the Docker image and rolls out the new container.

To deploy a specific commit:
1. Go to the Render dashboard
2. Click "Manual Deploy" → "Deploy a specific commit"
3. Enter the commit SHA

## Monitoring

### Health Check

Render.com pings `/health` every 30 seconds. If it fails 3 times in a row, Render will:
- Send an alert email
- Show the service as "degraded" in the dashboard
- (Free tier) NOT auto-restart the service

### Logs

View logs in the Render dashboard:
- "Logs" tab → see real-time logs
- "Events" tab → see deploy history

To see specific events:
- **Daily reset**: search for "Demo reset" in logs
- **Signup events**: search for "Signup stored" in logs
- **Platform errors**: search for "ERROR" in logs

### Metrics

Render.com shows basic metrics:
- CPU usage
- Memory usage
- Request count
- Response time

For detailed metrics, you'd need to add a metrics endpoint to the platform (currently not exposed in demo mode).

## Common Operations

### View signups

Signups are stored in `/data/signups/emails.csv` on the container's persistent disk.

To view them:
1. Go to Render dashboard → "Shell" tab
2. Run: `cat /data/signups/emails.csv`

To export:
1. Run: `cp /data/signups/emails.csv /tmp/emails.csv`
2. Download from Render's shell interface (or use `scp` if you have shell access)

### Manual reset

To manually reset the demo state (e.g., if something got into a bad state):

1. Go to Render dashboard → "Shell" tab
2. Run:
   ```bash
   # Stop the platform
   supervisorctl stop aegisgate-demo

   # Wipe runtime state (NOT seed data)
   find /data -mindepth 1 -maxdepth 1 -type d ! -name 'seed' -exec rm -rf {} +

   # Re-copy seed data
   cp -r /opt/aegisgate-demo/seed-data/* /data/seed/

   # Start the platform
   supervisorctl start aegisgate-demo
   ```

### Update sample data

1. Edit the JSON files in `seed-data/`
2. Commit and push to `main`
3. Render auto-deploys
4. The daily reset will pick up the new data within 24 hours
5. Or trigger a manual reset (see above) to apply immediately

### Update seed data without waiting for daily reset

The seed data is in `/opt/aegisgate-demo/seed-data/`. To apply changes immediately:

1. Go to Render dashboard → "Shell" tab
2. Run:
   ```bash
   # Backup current seed data
   cp -r /data/seed /data/seed.backup-$(date +%Y%m%d)

   # Copy new seed data
   cp -r /opt/aegisgate-demo/seed-data/* /data/seed/

   # Restart the platform to pick up the new data
   supervisorctl restart aegisgate-demo
   ```

### Add a new MCP tool

1. Edit `seed-data/mcp-tools.json`
2. Add a new tool object to the array
3. Commit and push
4. Render auto-deploys
5. The new tool will be available after the next daily reset (or manual reset)

### Update the daily reset interval

The daily reset is configured in `entrypoint.sh` via the `AEGISGATE_DEMO_RESET_HOURS` env var (default 24).

To change it:
1. Edit `render.yaml` (set `AEGISGATE_DEMO_RESET_HOURS` to the desired value)
2. Commit and push
3. Render redeploys

### Update rate limits

Rate limits are configured in:
- **nginx**: `nginx/nginx.conf` (per-IP, per-signup)
- **Signup server**: `email-signup/signup.py` (per-email)
- **AegisGate platform**: env var `AEGISGATE_DEMO_MAX_REQUESTS_PER_HOUR` in `render.yaml`

## Troubleshooting

### Demo is sleeping (free tier)

**Symptom**: First request after 15 minutes of inactivity takes ~30 seconds.
**Cause**: Render.com free tier sleeps services after 15 minutes of inactivity.
**Fix**: This is expected behavior on the free tier. To avoid the cold start, upgrade to Render's paid plan ($7/mo).

### Email signup is broken

**Symptom**: "Sign-in failed" error on the signup form.
**Diagnosis**:
1. Check Render logs for errors in the signup server
2. Test the signup endpoint directly: `curl -X POST https://demo.aegisgatesecurity.io/signup/submit -d '{"email":"test@example.com"}' -H "Content-Type: application/json"`
**Common causes**:
- Rate limit hit (try again in 1 hour)
- Email format invalid
- Disk full (signups CSV can't be written)

### AegisGate platform is down

**Symptom**: "502 Bad Gateway" or "Service Unavailable" when visiting the demo.
**Diagnosis**:
1. Check Render dashboard → "Logs" for platform errors
2. Check the platform's health endpoint: `curl https://demo.aegisgatesecurity.io/health`
3. If unhealthy, restart the service from the Render dashboard
**Common causes**:
- Platform crashed (check logs for panic)
- Out of memory (free tier has 512MB limit)
- Mock upstream (httpbin.org) is down

### DEMO MODE banner is not showing

**Symptom**: The 🛡️ DEMO MODE badge is missing from the top-right corner.
**Diagnosis**:
1. Check that nginx is running: `supervisorctl status nginx`
2. Check that the CSS/JS files are being served: `curl https://demo.aegisgatesecurity.io/__demo__/demo-banner.css`
3. Check the browser console for errors (F12)
**Common causes**:
- nginx is not running
- The `sub_filter` directive is not working
- The CSS/JS files are missing

### httpbin.org is rate-limiting us

**Symptom**: Many requests return 429 Too Many Requests.
**Cause**: httpbin.org has its own rate limits.
**Fix**: This is a known limitation of the demo. We're using a free public service. For a more reliable demo, you'd:
- Self-host a mock LLM service
- Use a paid mock service
- Cache responses in nginx

### Render.com free tier hours exceeded

**Symptom**: Render shows "Out of free tier hours" or similar.
**Cause**: Free tier is 750 hours/month. If the demo is accessed 24/7, you might exceed this.
**Fix**: Either:
- Upgrade to Render's paid plan ($7/mo)
- Accept that the demo may be unavailable near the end of the month
- Move to a different free host (Fly.io has 3 free VMs)

## Maintenance Windows

Recommended maintenance:
- **Weekly**: Check the signup CSV for any spam
- **Monthly**: Review the daily reset log for any errors
- **Quarterly**: Update the AegisGate platform image to the latest version

## Disaster Recovery

If something goes catastrophically wrong:

1. **Wipe everything**: Delete the service in Render, redeploy from scratch
2. **Restore from backup**: Signups are in `/data/signups/emails.csv` — if Render is down, you can recover this from Render's disaster recovery (they keep backups for 7 days on free tier)
3. **Contact Render support**: If Render itself is having issues

## Monitoring Alerts (Future)

For production-like monitoring, consider adding:
- Uptime monitoring (UptimeRobot, Pingdom)
- Error tracking (Sentry, Rollbar)
- Log aggregation (Datadog, Loggly)
- Status page (StatusPage, Better Uptime)

These are not currently set up for the demo but would be trivial to add.

## Contact

- **Demo issues**: hello@aegisgatesecurity.io
- **Security issues**: security@aegisgatesecurity.io
- **Render.com support**: https://render.com/support
- **AegisGate platform issues**: https://github.com/aegisgatesecurity/aegisgate-platform/issues
