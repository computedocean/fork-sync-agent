# 🔄 Fork Sync Agent

Keeps every fork you own up to date with its upstream, automatically, once a day.

It follows a simple loop:

```text
INSPECT  →  ACT  →  VERIFY  →  REPORT
```

1. **Inspect**: lists your forks and checks how many commits each one is behind upstream.
2. **Act**: asks GitHub to merge upstream into each fork's default branch.
3. **Verify**: re-checks every synced fork to confirm it's caught up.
4. **Report**: writes a summary table to the workflow run, and opens a tracking issue for any fork that needs a human, such as a merge conflict. The issue closes itself once everything syncs cleanly.

No dependencies: one Python file using only the standard library, plus one GitHub Actions workflow.

## Setup

1. **Create a fine-grained personal access token** at *GitHub → Settings → Developer settings → Fine-grained tokens*:
   - **Repository access:** All repositories
   - **Permissions:** Contents *Read and write*, Workflows *Read and write*, Issues *Read and write*
   - Workflows access is needed because upstream projects often change their `.github/workflows` files, and GitHub refuses to sync those without it.
2. In this repo, go to *Settings → Secrets and variables → Actions* and add a secret named **`FORK_SYNC_TOKEN`** with that token.
3. Optional: add a variable named **`FORK_SYNC_EXCLUDE`** with a comma-separated list of repo names to skip, for example forks you've customized and don't want touched.
4. Go to *Actions → Sync forks → Run workflow*, tick **dry run**, and check the summary before the first real run.

## Running locally

```bash
GH_TOKEN=$(gh auth token) DRY_RUN=true python sync_forks.py
```

## Notes

- It only touches each fork's **default branch**. Other branches are left alone.
- Archived forks are skipped.
- If a fork has its own commits, GitHub creates a merge commit. If the changes conflict, the fork is left untouched and listed in the tracking issue.
- GitHub pauses scheduled workflows in repos with no activity for 60 days. If that happens, re-enable the workflow from the Actions tab.

## What I learned

- Merge conflicts happen when a fork has commits the original doesn't.
- "Discard commits" on the Sync fork button fixes them.
