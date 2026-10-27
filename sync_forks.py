"""Fork sync agent: keeps every fork you own up to date with its upstream.

Inspect -> act -> verify -> report:
  1. Inspect: list your forks and check how far each is behind upstream.
  2. Act: ask GitHub to merge upstream into each fork's default branch.
  3. Verify: re-check that each synced fork is no longer behind.
  4. Report: write a job summary, and open (or close) a tracking issue
     for forks that need a human, such as merge conflicts.

Standard library only. Configuration comes from environment variables:
  GH_TOKEN      token with Contents + Workflows write on your forks (required)
  DRY_RUN       "true" to inspect and report without syncing
  EXCLUDE       comma-separated repo names to skip
  REPORT_REPO   owner/name to file the tracking issue in (optional)
"""
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
TOKEN = os.environ.get("GH_TOKEN", "")
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
EXCLUDE = {n.strip().lower() for n in os.environ.get("EXCLUDE", "").split(",") if n.strip()}
REPORT_REPO = os.environ.get("REPORT_REPO", "")
ISSUE_TITLE = "Fork sync: forks need attention"


def api(method, path, body=None):
    req = urllib.request.Request(
        path if path.startswith("http") else API + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
            return resp.status, json.loads(data) if data else {}, resp.headers
    except urllib.error.HTTPError as e:
        data = e.read()
        try:
            payload = json.loads(data) if data else {}
        except ValueError:
            payload = {"message": data.decode(errors="replace")}
        return e.code, payload, e.headers


def list_forks():
    forks, url = [], "/user/repos?affiliation=owner&per_page=100"
    while url:
        status, page, headers = api("GET", url)
        if status != 200:
            sys.exit(f"Could not list repos ({status}): {page.get('message')}")
        forks += [r for r in page if r["fork"] and not r["archived"]]
        url = next(
            (p.split(";")[0].strip(" <>") for p in (headers.get("Link") or "").split(",") if 'rel="next"' in p),
            None,
        )
    return [f for f in forks if f["name"].lower() not in EXCLUDE]


def behind_by(fork):
    """Commits the fork's default branch is missing from upstream, or None if unknown."""
    status, repo, _ = api("GET", f"/repos/{fork['full_name']}")
    parent = repo.get("parent") if status == 200 else None
    if not parent:
        return None, None
    # compare/BASE...HEAD: ahead_by counts upstream commits the fork doesn't have yet.
    fork_branch = f"{fork['owner']['login']}:{fork['default_branch']}"
    status, cmp, _ = api("GET", f"/repos/{parent['full_name']}/compare/{fork_branch}...{parent['default_branch']}")
    if status != 200:
        return None, parent
    return cmp.get("ahead_by"), parent


def sync(fork):
    status, body, _ = api("POST", f"/repos/{fork['full_name']}/merge-upstream", {"branch": fork["default_branch"]})
    if status == 200:
        return "synced", body.get("merge_type", "")
    if status == 409:
        return "conflict", body.get("message", "merge conflict")
    return "error", f"{status}: {body.get('message', '')}"


def file_report(needs_attention):
    if not REPORT_REPO:
        return
    status, issues, _ = api("GET", f"/repos/{REPORT_REPO}/issues?state=open&per_page=100")
    existing = next((i for i in issues if i["title"] == ISSUE_TITLE), None) if status == 200 else None
    if needs_attention:
        body = "These forks could not be synced automatically and need a look:\n\n" + "\n".join(
            f"- [{name}](https://github.com/{name}): {why}" for name, why in needs_attention
        )
        if existing:
            api("PATCH", f"/repos/{REPORT_REPO}/issues/{existing['number']}", {"body": body})
        else:
            api("POST", f"/repos/{REPORT_REPO}/issues", {"title": ISSUE_TITLE, "body": body})
    elif existing:
        api("PATCH", f"/repos/{REPORT_REPO}/issues/{existing['number']}", {"state": "closed"})


def main():
    if not TOKEN:
        sys.exit("GH_TOKEN is not set.")
    forks = list_forks()
    rows, needs_attention = [], []
    counts = {"up to date": 0, "synced": 0, "would sync": 0, "needs attention": 0}

    for fork in forks:
        name = fork["full_name"]
        behind, parent = behind_by(fork)
        if parent is None:
            rows.append((name, "needs attention", "upstream not found (deleted or private)"))
            needs_attention.append((name, "upstream not found"))
            counts["needs attention"] += 1
            continue
        if behind == 0:
            counts["up to date"] += 1
            continue
        detail = f"{behind} commits behind" if behind is not None else "behind (count unknown)"
        if DRY_RUN:
            rows.append((name, "would sync", detail))
            counts["would sync"] += 1
            continue

        result, info = sync(fork)
        if result == "synced":
            after, _ = behind_by(fork)
            verified = "verified" if after == 0 else f"still {after} behind"
            rows.append((name, "synced", f"{detail}, {info}, {verified}"))
            counts["synced"] += 1
        else:
            rows.append((name, "needs attention", info))
            needs_attention.append((name, info))
            counts["needs attention"] += 1

    mode = "DRY RUN" if DRY_RUN else "LIVE"
    summary = [f"## Fork sync ({mode})", "", f"Checked **{len(forks)}** forks.", ""]
    summary += [f"- {k}: **{v}**" for k, v in counts.items() if v]
    if rows:
        summary += ["", "| Fork | Result | Details |", "|---|---|---|"]
        summary += [f"| {n} | {r} | {d} |" for n, r, d in rows]
    text = "\n".join(summary)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(text + "\n")

    if not DRY_RUN:
        file_report(needs_attention)


if __name__ == "__main__":
    main()
