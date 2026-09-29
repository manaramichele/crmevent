# RCA — Deploy run fe3c3dfc-5fb0-4795-a281-b3e87de72ce7 (manage-events-12)

## Summary
Redeploy failed at the **build_image** step. Backend dependency install (`pip install -r /app/backend/requirements.txt`) aborted because a requirements entry points at a package version that does not exist on PyPI.

## Failing step
`build_image` — Cloud Build, backend-build layer 13/13.

## Evidence
Build log:
```
ERROR: Could not find a version that satisfies the requirement lintiq==0.1.3 (from versions: none)
ERROR: No matching distribution found for lintiq==0.1.3
[RETRY] All 3 attempts failed
process "... pip install --no-cache-dir --no-dependencies -r /app/backend/requirements.txt" did not complete successfully: exit code: 1
```

Sandbox verification (eph pod, run source at /app/scratch):
- `backend/requirements.txt` lines 59–60:
  ```
  librt==0.15.0
  lintiq==0.1.3
  ```
- `pip index versions lintiq` → `ERROR: No matching distribution found for lintiq` (package does not exist on PyPI).
- `grep -rnE 'import lintiq|from lintiq|import librt|from librt'` across backend → **NO IMPORTS FOUND**. Neither package is used anywhere in the code.
- `librt==0.15.0` did resolve/download in the build (harmless), but is also unused; `lintiq==0.1.3` is the hard blocker.

## Root cause
Two phantom/hallucinated dependencies were added to `backend/requirements.txt`. `lintiq==0.1.3` is unresolvable on PyPI, which fails the pip install and the entire build. Both packages are unreferenced in the source.

## Fix (Code — E1)
Edit `backend/requirements.txt` and remove the unused/nonexistent lines:
- Remove line 60: `lintiq==0.1.3` (required — build blocker)
- Remove line 59: `librt==0.15.0` (recommended — unused phantom dep)

Then redeploy. No manifest, secret, tier, or infra change is required — the previous run (f2fe1de4, same template/tier) built and is live, so the environment is healthy.

## Not manifest-caused
This is a user-source dependency error, not a base-image/entrypoint/nginx issue. No manifest edit applies; resume_pipeline was intentionally not called.
