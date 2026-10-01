# Ghost Trail RBAC / Security Fix

## Roles
- **viewer**: read cameras, people, alerts, sightings, dashboard telemetry, and authenticated camera streams.
- **analyst**: viewer + face-review decisions, alert dismissal, and security-profile edits.
- **admin**: analyst + camera/config changes, enrollment, deletion, and audit-log access.

## Authentication
- FastAPI issues signed, expiring tokens using an HMAC-SHA256 token format.
- Passwords use PBKDF2-HMAC-SHA256 with a unique salt and 240,000 iterations.
- A local secret is generated on first start and stored outside source code. `GHOST_TRAIL_AUTH_SECRET` can override it for deployment.
- First launch creates an administrator. Set `GHOST_TRAIL_ADMIN_USERNAME` and `GHOST_TRAIL_ADMIN_PASSWORD` before deployment. If no password is supplied, a random bootstrap password is printed and written to `auth_bootstrap.txt`; change it before deployment.

## Protected surfaces
All REST data endpoints require an authenticated role. Mutating endpoints require analyst/admin or admin as documented above. MJPEG camera streams and `/api/ws` require a valid token.

## Audit
Security-sensitive operations are written to `auth.db` and exposed to administrators through `GET /api/audit`.

## Frontend
Axios automatically attaches the bearer token. The WebSocket and authenticated image/stream URLs also carry the session token. A 401 response clears the local session and returns the operator to the login screen.
