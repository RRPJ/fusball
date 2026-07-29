# Authentication And Authorization

## Production Contract

Hosted production uses strict Clerk authentication:

- Vercel runs with `FUSBALL_AUTH_MODE=clerk`.
- Clerk verifies the individual session and immutable provider subject.
- Neon `app_users` rows determine whether that subject is active and which
  application role it has.
- Legacy PIN and token headers are ignored in strict mode.

API clients present the Clerk session token as
`Authorization: Bearer <session-token>`. The phone UI obtains and sends that
token automatically after sign-in.

This separates identity from application policy. A user can be disabled or
have their role changed without rotating a credential shared by every
operator.

Static assets and `GET /api/health` remain public. The `/phone` client hides
operational content until Clerk resolves, but that UI gate is not the security
boundary: every protected `/api/*` route authorizes the request server-side.
Anonymous strict-mode visits are sent to `/login`, and the login `next` value
is restricted to a local path.

## Roles

| Role | Permissions |
| --- | --- |
| `reader` | Leaderboard, player, history, profile, stats, presence, and odds reads |
| `operator` | All reader permissions plus player creation, presence changes, lineup helpers, and match submission |
| `admin` | All operator permissions plus match listing, void, and restore |

There is no role-administration API. Provisioning and role changes are
controlled database operations. Only rows with `status='active'` authorize
access. `display_name` is informational; authorization always uses the Clerk
`provider_subject`.

## Required Hosted Configuration

Set these separately for Vercel Preview and Production:

- `DATABASE_URL`: the matching Neon database
- `FUSBALL_AUTH_MODE=clerk`: set explicitly; the code default is `legacy`
- `CLERK_SECRET_KEY`: backend verification key
- `CLERK_PUBLISHABLE_KEY`: browser integration key
- `CLERK_AUTHORIZED_PARTIES`: comma-separated exact frontend origins
- `CLERK_FRONTEND_API_URL`: optional compatibility fallback used when the
  frontend origin cannot be derived from the publishable key

Production must use production credentials and the production origin. Preview
must use an isolated Neon branch/project and Clerk configuration that accepts
the exact preview origin. Never put a production Neon URL into Vercel Preview.
Do not commit any of these values.

## Provisioning Application Users

Apply migrations first:

```powershell
python scripts\migrate_neon_schema.py --database-url "<database-url>" --apply
```

Obtain the immutable `user_...` subject from the Clerk dashboard or a verified
session, then insert the least-privileged role required:

```sql
INSERT INTO app_users (provider_subject, display_name, role, status)
VALUES ('user_...', 'Operator name', 'operator', 'active');
```

Change a role:

```sql
UPDATE app_users
SET role = 'admin', updated_at = NOW()
WHERE provider_subject = 'user_...';
```

Disable access while preserving audit attribution:

```sql
UPDATE app_users
SET status = 'disabled', updated_at = NOW()
WHERE provider_subject = 'user_...';
```

`GET /api/auth/me` returns the resolved subject, display name, and role for an
active managed session. A valid Clerk identity without an active `app_users`
row is not authorized.

## Compatibility Modes

`FUSBALL_AUTH_MODE` accepts:

- `clerk`: production standard; managed identity only.
- `hybrid`: managed identity first, with configured PIN/token fallback. Use
  only for a time-bounded rollback or transition.
- `legacy`: PIN/token behavior only. This is the local-development default.

In `hybrid` and `legacy`, `READ_PIN_HASH`, `WRITE_PIN_HASH`, and
`FUSBALL_PHONE_API_TOKEN` retain compatibility behavior. They are not a
substitute for individual production identity. Remove fallback secrets from
hosted configuration after strict Clerk validation.

## Rollout Validation And Evidence

The repository implements and tests strict Clerk behavior, but it cannot prove
external provider setup or deployment completion. Before declaring an
environment ready, record:

1. Vercel deployment URL/ID and commit SHA.
2. Redacted environment mapping showing strict mode and the intended Neon
   environment.
3. Clerk authorized-party configuration for the exact origin.
4. Successful sign-in and `GET /api/auth/me` results for each provisioned role.
5. Negative checks: anonymous access rejected, reader writes rejected, disabled
   users rejected, and legacy headers rejected in strict mode.
6. Operator write and admin correction checks against isolated preview data.

Do not publish session tokens, Clerk secrets, database URLs, or screenshots
containing them as rollout evidence.

## See Also

- `development.md`
- `phone-api.md`
- `phone-write-policy.md`
