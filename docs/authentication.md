# Authentication And Authorization

## Decision

Clerk is the managed identity provider for hosted Vercel deployments. Clerk
verifies who signed in and manages session lifecycle. Fusball remains
responsible for authorization through the Neon `app_users` table.

This keeps provider identity separate from application policy and allows one
user to be disabled or have their role changed without rotating a shared
credential.

Alternatives considered:

- Auth0 provides mature enterprise identity and audit features, but adds cost
  and operational complexity that are not justified for the current user base.
- Neon Auth is closely aligned with the database but has less mature Flask
  integration and application-level authorization support.

Revisit this decision if enterprise SSO, contractual compliance controls, or a
materially different client architecture becomes necessary.

## Roles

| Role | Permissions |
| --- | --- |
| `reader` | Read leaderboards, players, history, profiles, stats, and odds |
| `operator` | All reader permissions plus player, presence, lineup, and match writes |
| `admin` | All operator permissions plus match void/restore and role administration |

Only active rows in `app_users` authorize access. The immutable Clerk subject
is the primary key; display names are informational and must not be used for
authorization.

## Rollout Modes

Set `FUSBALL_AUTH_MODE` to:

- `legacy`: current PIN/token behavior only; local-development default.
- `hybrid`: Clerk identity first, with configured PIN/token fallback during
  deployment rollback.
- `clerk`: managed identity only; legacy headers are ignored.

Hosted production should move from `hybrid` to `clerk` after the login UI and
rollback checks are complete. Do not leave hybrid mode enabled indefinitely.

Phone-page UX by mode:
- `clerk`: `/phone` resolves the Clerk browser session before initializing the
  application. Anonymous visitors are redirected to the dedicated `/login`
  page, and successful sign-in returns them to `/phone`. Signing out returns
  them to `/login`.
- `hybrid`: managed login is shown prominently, with the PIN fallback and
  read-PIN behavior still available.
- `legacy`: unchanged PIN/token UI.
- In every mode, static assets (`/static/*`) and `GET /api/health` are
  unaffected by client-side gating, and every `/api/*` route still enforces
  authorization server-side regardless of what has rendered client-side.

The login route accepts a local `next` path and defaults to `/phone`. External
or otherwise unsafe destinations are rejected to prevent open redirects.

To validate the final managed-auth experience before production rollout, set
`FUSBALL_AUTH_MODE=clerk` only for the Vercel Preview environment and redeploy.
Production can remain in `hybrid` during this check.

Required hosted configuration:

- `CLERK_SECRET_KEY`
- `CLERK_PUBLISHABLE_KEY` for the browser login integration
- `CLERK_FRONTEND_API_URL`, an optional compatibility fallback; the instance
  origin is normally derived from `CLERK_PUBLISHABLE_KEY` as Clerk recommends
- `CLERK_AUTHORIZED_PARTIES`, a comma-separated allowlist of exact frontend
  origins
- `DATABASE_URL`

Clerk's authorized-parties check is mandatory because it protects against
session-cookie leakage across subdomains.

## Application Users

Apply schema migrations, then add a user using the immutable subject shown by
Clerk:

```sql
INSERT INTO app_users (provider_subject, display_name, role)
VALUES ('user_...', 'Operator name', 'operator');
```

Disable access without deleting audit identity:

```sql
UPDATE app_users
SET status = 'disabled', updated_at = NOW()
WHERE provider_subject = 'user_...';
```

`GET /api/auth/me` returns the resolved subject, display name, and role for a
valid managed session.
