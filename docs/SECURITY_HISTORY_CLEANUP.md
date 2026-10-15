# Security History Cleanup (Local Operator Procedure)

This PR improves future hygiene but **does not rewrite already-pushed Git history**.
Anything previously pushed must be treated as potentially public.

If you need to purge historical sensitive/runtime artifacts, do it locally with history rewrite and then force-push.

## Target paths to purge

- `backend/memory/memory.json`
- `backend/memory/conversation_log.json`
- `backend/memory/activity_log.json`
- `backend/screenshots/`

## Procedure

1. Install `git-filter-repo` (one-time).
2. Work in a clean local clone with no uncommitted changes.
3. Rewrite history:

```bash
git filter-repo \
  --path backend/memory/memory.json \
  --path backend/memory/conversation_log.json \
  --path backend/memory/activity_log.json \
  --path backend/screenshots \
  --invert-paths
```

4. Verify removal:

```bash
git log -- backend/memory/memory.json backend/memory/conversation_log.json backend/memory/activity_log.json backend/screenshots
```

5. Force-push rewritten refs (coordinate with collaborators first):

```bash
git push --force --all origin
git push --force --tags origin
```

6. Rotate any exposed credentials/secrets immediately and invalidate old keys.

## Important warning

History rewrite changes commit SHAs and requires collaborators to re-sync/re-clone.
Only perform this with explicit team coordination.
