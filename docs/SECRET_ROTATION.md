# Secret rotation & git history purge (runbook)

Use this after credentials were committed (see `docs/SECURITY_SCALABILITY_AUDIT.md` Phase 0).

## 1. Rotate credentials (do this first)

1. **Render** — regenerate `SECRET_KEY` / `JWT_SECRET_KEY` (or set new values in the dashboard).
2. **Upstash Redis** — reset password / create a new database URL; update `REDIS_URL`.
3. **Cloudinary** — rotate API secret; update `CLOUDINARY_*` env vars.
4. **Users** — force password reset for any accounts whose hashes lived in a committed `injaaz.db`.

Until rotation is done, treat any clone of this repo as credential-compromised if shared outside the team.

## 2. Stop tracking secrets going forward

Already handled in-repo:

- `.gitignore` ignores `.env.*`, `*.db`, `instance/`
- Files were removed from the index with `git rm --cached` (history still contains them until step 3)

## 3. Purge from git history (later; coordinated)

Requires team coordination and a force-push. Example with [git-filter-repo](https://github.com/newren/git-filter-repo):

```bash
# Backup the repo first, then:
pip install git-filter-repo
git filter-repo --path .env.production --path injaaz.db --path instance/injaaz.db --invert-paths
git remote add origin <YOUR_REMOTE_URL>
git push --force --all
git push --force --tags
```

Every collaborator must **re-clone** (or hard-reset to the rewritten history). Do not run this casually on a shared `main` without agreement.

## 4. Verify

- `git log --all --full-history -- .env.production injaaz.db` returns nothing after purge
- App boots with new secrets from the host environment only
- Login still works after user password resets
