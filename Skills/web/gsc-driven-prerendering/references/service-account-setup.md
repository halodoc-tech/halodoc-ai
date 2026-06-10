# Service Account Setup for GSC Prerender

The runner script authenticates to Google Search Console using a Google Cloud **service account**. It needs a JSON key file at `$GSC_KEY_DIR/gsc-service-account.json`.

This is a one-time setup per GSC property. If your project already has a service account with GSC access in CI, ask the owner to share access rather than creating a new one.

---

## 1. Create a service account in Google Cloud

1. Open the GCP project that should own the credential. Use a dedicated project for SEO automation if you have one — avoid a personal sandbox.
2. **IAM & Admin → Service Accounts → Create Service Account**.
3. Name it descriptively, e.g. `gsc-prerender-reader`.
4. Skip role assignment at the project level — GSC permissions are granted in Search Console, not GCP.
5. Open the new service account → **Keys → Add Key → Create new key → JSON**. Save the file as `gsc-service-account.json`.

> Treat this file like a password. Never commit it. Add `gsc-service-account.json` to `.gitignore` if the file might land in the repo during local development.

---

## 2. Enable the Search Console API

In the same GCP project:

**APIs & Services → Library → "Google Search Console API" → Enable.**

Without this, calls return `403 SERVICE_DISABLED` even with a valid key.

---

## 3. Grant the service account access to the GSC property

Search Console permissions are granted **per property**, not at the GCP level.

1. Open [Google Search Console](https://search.google.com/search-console) as a property owner.
2. Pick the property whose data should drive prerendering. The script's `GSC_SITE_URL` must match the registered protocol/host exactly (`https://www.example.com` ≠ `https://example.com` — they're separate properties).
3. **Settings → Users and permissions → Add user.**
4. Email address: the service account's email (looks like `gsc-prerender-reader@<gcp-project>.iam.gserviceaccount.com`).
5. Permission level: **Restricted** (read-only) is enough — the script only calls `searchanalytics.query`.

---

## 4. Wire the key into local + CI environments

### Local development

Place the JSON file outside the repo, e.g. `~/.config/gsc-keys/gsc-service-account.json`, and export:

```bash
export GSC_KEY_DIR="$HOME/.config/gsc-keys"
```

Then `npm run gsc-prerender` will pick it up. Add the export to your shell profile or use `direnv` per repo.

### CI (GitHub Actions / GitLab CI / Jenkins / etc.)

The host project is responsible for materialising the key. Typical pattern:

1. Store the JSON contents as a CI secret (GitHub Actions secret, GitLab CI file variable, Jenkins Secret file, Vault secret, etc.).
2. In the job, write the secret to a temp directory and export `GSC_KEY_DIR` pointing at that directory.
3. After the script runs, the temp directory is discarded with the workspace.

> The script only reads `$GSC_KEY_DIR`. Anything that gets the file there with the right name (`gsc-service-account.json`) works — Vault sidecar, AWS Secrets Manager → file, sealed secret, etc.

---

## 5. Verify the credential

A 5-second smoke test before wiring the script into a real route:

```bash
GSC_KEY_DIR=/path/to/dir node -e "
import('googleapis').then(async ({ google }) => {
  const auth = new google.auth.GoogleAuth({
    keyFile: process.env.GSC_KEY_DIR + '/gsc-service-account.json',
    scopes: ['https://www.googleapis.com/auth/webmasters.readonly'],
  });
  const sc = google.searchconsole({ version: 'v1', auth: await auth.getClient() });
  const res = await sc.sites.list();
  console.log(res.data);
});"
```

You should see your verified properties listed. If the property you need is missing, the service account hasn't been added in Search Console (Step 3).

---

## Common errors

| Symptom | Cause | Fix |
|---|---|---|
| `Failed to create Search Console client. Place service account key at /…/gsc-service-account.json` | `GSC_KEY_DIR` unset or path wrong | Export `GSC_KEY_DIR`; confirm the JSON file is named exactly `gsc-service-account.json`. |
| `403 SERVICE_DISABLED` | Search Console API not enabled in the GCP project | Enable it (Step 2). |
| `403 User does not have sufficient permission for site` | Service account not added to the GSC property, or the `GSC_SITE_URL` host/protocol doesn't match | Re-add in GSC; confirm `https://` vs `http://` and `www` vs apex. |
| Empty `rows` array but no error | Query window has no traffic, or the regex matches nothing | Widen the date range; double-check the regex against real URLs in GSC's "Performance" report. |
