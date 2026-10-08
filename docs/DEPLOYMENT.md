# Free accountant pilot hosting

Run one **Render Free Python web service** with a separate **Supabase Free or Neon Free PostgreSQL database**. The 20-case, five-company pilot and accountant access are handled by IntelliAudit. This application uses its own invitation/session authentication; it does not require Supabase Auth.

The hosted server requires a database connection and an administrator access code. It refuses to fall back to temporary SQLite storage. Accounts, sessions, frozen review plans, and review events survive Render sleep and redeploys in PostgreSQL. Browser drafts remain local to the accountant's browser until submitted.

## Create the database

Create a dedicated PostgreSQL project in your personal organization. Keep its plan **Free**. Avoid reusing an unrelated organizational application database.

- **Supabase:** use the dashboard's Connect dialog and copy a **session pooler** connection string (IPv4-compatible, port 5432) or transaction pooler string (port 6543). Replace the password placeholder with the actual database password and percent-encode special password characters. Include `sslmode=require`. IntelliAudit disables prepared statements for transaction-pooler compatibility. Do not enable the `intelliaudit` schema in the Data API.
- **Neon:** use the connection dialog's pooled PostgreSQL URL with `sslmode=require`. Keep the plan Free; do not enable paid extras.

The database owner connection creates a private `intelliaudit` schema at startup. It grants no public schema access. Review events have UPDATE/DELETE rejection triggers and a database transaction lock preserves protocol transitions between server processes. Keep the database connection URL on the server only.

## Create the Render service

1. Sign in to Render and create a Web Service using `https://github.com/manmad-web/IntelliAudit` and branch `codex/accountant-review-dashboard`. Alternatively, create a Blueprint from the repository's `render.yaml`.
2. Select **Python**, region **Oregon**, and compute plan **Free**. The checked-in Blueprint explicitly selects Free and creates no paid disk or database.
3. Set the build command to `pip install -r requirements-hosted.txt`.
4. Set the start command to `python -m dashboard.server --hosted --host 0.0.0.0 --port $PORT` and health check path to `/healthz`.
5. Supply these environment variables through Render's secret settings:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | The complete TLS PostgreSQL pooler connection URL |
| `APP_ORIGIN` | Optional on Render: automatically uses `RENDER_EXTERNAL_URL`. For another host or custom domain, set the exact HTTPS URL with no trailing slash. |
| `ADMIN_ACCESS_CODE` | A random, private administrator access code of at least 32 characters |
| `PYTHON_VERSION` | `3.12.14` |

6. Deploy and check `/healthz`, then open the HTTPS application. Keep automatic deployment disabled during an active review round so every accountant sees the frozen corpus.

Keep passwords, administrator codes, invitation codes, session tokens, reviewer exports, and `.env` files out of Git. Use Render's environment variable editor; do not paste credentials into GitHub issues or build commands.

## Verify and share

Before distributing the URL, verify two independent test accounts in a disposable study database. Confirm unauthenticated review requests are denied, proposals remain unavailable before all 20 initial submissions, and a redeploy retains accounts, frozen plans and submissions. Keep software test events outside the actual accountant study.

The current `pilot-v2` study keeps each first assessment immutable and opens generated proposals immediately after all 20 initial cases are submitted. Agreement, revision or unresolved feedback is a separate record. It does not measure independent delayed repeat reliability. Earlier frozen v1 plans preserve their seven-day, three-case repeat requirement; the curator version selector can inspect that historical packet. Share the HTTPS URL plus a separate invitation code with each accountant. Keep the administrator code private. Invitations are credentials, so share them directly with their intended accountant.

The reviewer sees income-statement tables, explicit synthetic-source limitations, a short guide and a fictional practice case that saves no study records. Standards details can remain unresolved. The curator sees source provenance and construction checks separately; missing original filing accessions, qualifications and domain validation remain human review requirements.

Export and securely back up submitted reviews after each review session. Hosting and a completed review workflow do not by themselves establish a publication-ready benchmark or adjudicated gold labels.

## Free-plan limits

Render free web services sleep after 15 idle minutes; the next visitor may wait about a minute. Their local filesystem is erased on sleep, restart, and redeploy. Free Render Postgres expires after 30 days, so it is not used here. [Render free-plan documentation](https://render.com/docs/free)

Supabase Free currently includes 500 MB database storage, pauses after one week without activity, and does not include automatic backups. [Supabase pricing](https://supabase.com/pricing)

Neon Free currently includes 1 GB database storage per project, 100 CU-hours per project each month, and 5 GB monthly public transfer. Its compute suspends after five idle minutes and resumes on connection; its free restore history is limited. [Neon plans](https://neon.com/docs/introduction/plans)

These allowances comfortably fit a small accountant pilot, provided traffic and storage remain within the free limits. Review provider settings and quotas before each study round. No paid resource is needed for this configuration.

## Optional database integration verification

Install `requirements-hosted.txt` and set `TEST_DATABASE_URL` to a dedicated test database URL. Then run `python -m unittest discover -s tests -p test_postgres_store.py`. The integration test creates and drops only a generated `intelliaudit_test_...` schema; it never uses or removes the production `intelliaudit` schema. Without that test URL, external database integration tests are skipped.
