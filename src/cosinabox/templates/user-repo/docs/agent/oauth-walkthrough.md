# Google OAuth walkthrough

> **Last validated against Google Cloud console UI on 2026-04-12.**
> If steps are stale, run `cosinabox upgrade-docs` to refresh, or report at https://github.com/cosinabox/cosinabox/issues.

This script walks the user through getting a Google OAuth refresh token for Gmail + Calendar. The agent reads each step *one at a time* and waits for the user's confirmation before moving to the next.

## Re-auth: token expired

If `auth_health` Telegrammed you that a Google token expired, you do **not** need to repeat the manual GCP-console steps below. Run:

```bash
cosinabox auth refresh
```

This pulls your OAuth client creds from Railway, runs consent in your browser, writes the new refresh token back to Railway, and redeploys. If you have multiple Google accounts, it'll ask which one. If exactly one, it auto-selects.

Use the manual flow below only when:
- you're setting up a brand-new CoS for the first time, or
- you're not deploying to Railway (AWS / Fly support is on the roadmap), or
- `cosinabox auth refresh` itself errors out.

## First-time setup (manual GCP console flow)

## Why this is manual

Google OAuth requires manual clicks in the GCP console. There is no API to automate this for the consumer flow. Plan ~15 minutes.

## Prerequisites

- A Google account (the one whose Gmail + Calendar your CoS will read)
- A web browser
- A terminal with `cosinabox` installed

## Steps

1. **Open the GCP console.** Go to https://console.cloud.google.com/. Sign in with the account whose Gmail + Calendar you want CoSinaBox to access.

2. **Create a project (or use an existing one).** Click the project picker in the top bar → "New Project". Name it `my-cos` (or anything). Click "Create". Wait for the notification that the project is ready, then select it.

3. **Enable the Gmail API.** Go to https://console.cloud.google.com/apis/library/gmail.googleapis.com → click "Enable". Wait ~30 seconds.

4. **Enable the Calendar API.** Go to https://console.cloud.google.com/apis/library/calendar-json.googleapis.com → click "Enable".

5. **Configure the OAuth consent screen.** Go to APIs & Services → OAuth consent screen.
   - User Type: **External**. Click "Create".
   - App name: `my-cos`
   - User support email: your email
   - Developer contact: your email
   - Click "Save and continue" through the next pages without changing anything.
   - On "Test users", add your own email. Click "Save and continue".

6. **Create OAuth credentials.** Go to APIs & Services → Credentials → Create Credentials → OAuth client ID.
   - Application type: **Desktop app**
   - Name: `my-cos`
   - Click "Create".
   - Copy the **Client ID** and **Client Secret** that pop up.

7. **Set the env vars in `.env` (locally).**

   ```bash
   echo "GOOGLE_OAUTH_CLIENT_ID=<paste client id>" >> .env
   echo "GOOGLE_OAUTH_CLIENT_SECRET=<paste client secret>" >> .env
   ```

8. **Run the cosinabox auth flow.**

   ```bash
   cosinabox auth google
   ```

   This opens a browser tab to Google's OAuth consent screen. Sign in with the same account you used in step 1. Approve the requested scopes (gmail.modify, calendar). The browser will redirect to a localhost URL — that's expected. The terminal will print:

   ```
   GOOGLE_OAUTH_REFRESH_TOKEN=1//0gXXXXXX...
   ```

9. **Save the refresh token to `.env`.**

   ```bash
   echo "GOOGLE_OAUTH_REFRESH_TOKEN=1//0gXXXXXX..." >> .env
   ```

10. **Verify it works.**

    ```bash
    cosinabox doctor
    ```

    Look for `oauth_expiring`: should be green (refresh token is fresh).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "Access blocked: This app's request is invalid" | Consent screen not configured | Re-do step 5 |
| "Error 403: access_denied" | Test user not added | Add your email under step 5 "Test users" |
| `cosinabox auth google` hangs | Firewall blocks localhost callback | Run from a machine where localhost:8080 is reachable |
| `oauth_expiring` flagged red | Token already stale | Re-run `cosinabox auth google` |
