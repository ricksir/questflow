---
name: questflow-release
description: "Prepare and validate QuestFlow Studio/Mobile releases when a request includes a hotfix, version bump, update ZIP, APK, checksum, rollback, release report, or installable delivery. Do not use for diagnosis or ordinary code changes that do not request a release."
---

# QuestFlow Release

Produce an installable, traceable QuestFlow release without modifying the user's installed copy or exposing persistent data.

## Establish the baseline

- Work from the repository/source root, never from `C:\Users\user\QuestFlow` unless the user explicitly designates that folder as the source.
- Read `VERSION.txt`, `mobile/package.json`, the latest release manifest and the relevant tests.
- Confirm the requested Studio and Mobile versions. If the user requests only one platform, keep the other platform unchanged unless compatibility requires a coordinated change.
- Inspect existing release helpers such as `release_tools.py`, updater scripts and validation scripts before creating new packaging logic.

## Implement the requested change

- Keep the change scoped to the user's requested behavior.
- Preserve the invariants in the repository `AGENTS.md`, especially data compatibility, sync idempotency and source/install separation.
- Add or update regression tests for the behavior that caused the release.
- Update all user-visible version surfaces from the canonical version source; search for stale version literals before packaging.

## Validate and package

Read [references/release-checklist.md](references/release-checklist.md) before building artifacts. Apply only the gates relevant to the changed surfaces, but run the complete required release gates before claiming a final release.

- Generate distributable files in `../outputs/` unless the user specifies another destination.
- Validate the update against an isolated temporary copy, not the live installation or live database.
- Verify archive contents and checksums after the artifact is finalized.
- Build an APK only if Mobile changed or the user explicitly requests it. External build services, credentials and networked publication remain subject to the user's authorization.

## Report truthfully

- State exactly which checks ran, passed, failed or were unavailable.
- Do not call a source archive an APK or claim installation/device smoke testing without executing it.
- Provide clickable absolute paths for every artifact, plus versions, SHA-256, compatibility/rollback notes and any remaining limitation.
