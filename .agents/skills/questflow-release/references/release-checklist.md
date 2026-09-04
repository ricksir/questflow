# QuestFlow release checklist

Use this reference when preparing an installable Studio or Mobile release. Commands assume the source root as the current directory; adapt the Python executable to the available project runtime.

## 1. Baseline and consistency

- Read `VERSION.txt` and `mobile/package.json`.
- Review the latest `CHANGELOG.md`, `MANIFEST_UPDATE_*.json`, `RELEASE_MANIFEST_*.json` and compatibility matrix.
- Search for stale user-visible versions in `web`, `mobile`, manifests, scripts and documentation.
- Confirm whether a database migration exists and test both first application and repeated application.

Suggested searches:

```powershell
rg -n "Versão|Mobile [0-9]|build [0-9]|version" web mobile *.json *.md
rg -n "data|backups|runtime|\.venv|node_modules|\.git" release_tools.py questflow_*updat* installer.py
```

## 2. Code quality and tests

Run the directly related regression tests first. For a final release, run the applicable full gates:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pyright
npm --prefix web-src run typecheck
npm --prefix mobile run typecheck
npm --prefix mobile run test:core
```

If a tool is not installed in the project environment, record that fact and use the configured bundled runtime or the project's documented alternative. Do not silently omit the gate.

For Mobile release candidates, also run Expo Doctor and the appropriate Android build/smoke workflow. Building through EAS or another external service may require network access and credentials.

## 3. Artifact rules

Studio update names use the form:

```text
QuestFlow_Studio_<studio-version>_UPDATE.zip
```

Mobile artifacts use:

```text
QuestFlow_Mobile_<mobile-version>.apk
```

The Studio ZIP must have one `QuestFlow/` package root and must exclude at least:

```text
data
.venv
venv
runtime
backups
work
node_modules
.expo
.git
__pycache__
.pytest_cache
*.pyc
*.sqlite
*.db
.env*
keystores and service credentials
```

Include version metadata, update/release manifest, compatibility/rollback instructions and the code needed by the safe updater.

## 4. Isolated update validation

- Create a temporary installation and a disposable representative database.
- Exercise backup, staging, manifest validation, update, startup smoke test and rollback.
- Confirm that preserved directories and database records survive unchanged.
- Test paths containing spaces and long Windows paths when updater code changes.
- Never use the live `C:\Users\user\QuestFlow\data` database as the test target.

## 5. Final integrity

- Reopen the finalized ZIP and inspect its file list.
- Recompute SHA-256 after the last write.
- Confirm the checksum against the delivered checksum file.
- Confirm Studio and Mobile display the same versions declared in their manifests.
- Record counts/results of tests without inflating or inferring them.
- Deliver update instructions, rollback procedure and exact artifact paths.
