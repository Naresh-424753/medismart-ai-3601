# Go-live security checklist (real patient data)

Code alone does not make a health app safe for real patients. Do every step below; tick them off.
This is a technical checklist, not legal advice.

## 1. Render (backend) environment
| Variable | Value |
|---|---|
| `DEV_MODE` | `0` |
| `REAL_PATIENT_DATA` | `1`  (API refuses to start if anything below is unsafe) |
| `MONGO_URL` | your MongoDB Atlas string |
| `JWT_SECRET` | 48+ random characters (Render can generate it) |
| `DATA_KEY` | 32+ random characters. **Back it up offline.** Lose it = encrypted files unreadable |
| `SEED_DEMO` | `0` |
| `CORS_ORIGINS` | only your real `https://` frontend URL |
| `BREVO_API_KEY` (or `SMTP_*`) | so OTP emails actually arrive |
| `TRUSTED_PROXY_HOPS` | `1` (Render only) or `2` (Cloudflare in front) |
| `ADMIN_IP_ALLOWLIST` | optional: office / home static IPs |
| `GEMINI_API_KEY` | a **new** key. Rotate any key that was ever pasted in chat, email or git |

Generate secrets: `python -c "import secrets;print(secrets.token_urlsafe(48))"`.
Check: log in as admin, open `GET /admin/system-check` - `env_problems` must be empty.

## 2. MongoDB Atlas
- Paid cluster (M10+) for **encryption at rest, continuous backups and point-in-time restore**. The free tier has no backups.
- Database user with the least rights (readWrite on one database), not Atlas admin.
- Network access: allow only Render's outbound IPs (or use Private Link on paid plans), never `0.0.0.0/0` for real data.
- Turn on Atlas audit logs and alerts. Test a restore once.

## 3. Cloudflare (free tier) in front of Render and Vercel
WAF managed rules, bot fight mode, DDoS protection, rate-limit rules on `/auth/*`, TLS "Full (strict)", minimum TLS 1.2 (1.3 enabled), HSTS. Then set `TRUSTED_PROXY_HOPS=2`.

## 4. Vercel (frontend)
Security headers (CSP, HSTS...) are already in `frontend/vercel.json`. After deploy, open the site with the browser console open and check for CSP errors on: login, video call, maps, photo upload. 2FA on your Vercel, Render, GitHub, Atlas and Cloudflare accounts.

## 5. Monitoring and scanning
- Uptime + alerts: UptimeRobot / Better Stack on `/health`.
- GitHub: enable Dependabot, secret scanning and push protection.
- Before launch: `pip-audit` and `npm audit`, then a **professional penetration test**.
- Review `GET /admin/security-alerts` and `GET /admin/audit-logs/verify` weekly; save the `head_hash` somewhere outside the database.

## 6. India: DPDP Act 2023 (confirm current rules with a lawyer)
- Show a clear privacy notice and take **explicit consent** before collecting health data; allow withdrawal (the account-deletion and data-export screens exist).
- Collect only what you need; define how long you keep each kind of data and delete after that.
- **Breach**: notify the Data Protection Board and affected users. `POST /admin/breach-notice` notifies users; have a written incident plan.
- Name a grievance officer / contact; publish it on the site.
- Children: verifiable parental consent for under-18 users.
- Hospitals using this are the "data fiduciary"; sign a data-processing agreement with them. Keep patient data in India unless the rules allow otherwise.
- This project is demo software, **not a certified medical device**: keep the disclaimers, never present AI output as a diagnosis.

## 7. Known limits of this code (be honest with hospitals)
- The login token is kept in the browser (localStorage) and sent as a Bearer token. A future XSS bug could steal it. Moving to httpOnly cookies needs the API and site on one domain (e.g. `api.yourdomain.com` + `app.yourdomain.com`) - do that when you buy a domain.
- Medical records are protected by Atlas encryption at rest and TLS, not by per-field encryption in MongoDB. Uploaded documents are AES-256-GCM encrypted by the app.
- No third-party security audit has been done.
