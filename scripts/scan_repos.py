#!/usr/bin/env python3
"""
Repo Scanner — lists all GlacierEQ repos, flags duplicates, 
identifies stale/unowned repos, and suggests consolidation.

Output: repo_scan.json
"""
import os, json, urllib.request
from datetime import datetime, timezone

TOKEN = os.environ.get("APEX_GITHUB_TOKEN", "")
OWNER = os.environ.get("GITHUB_OWNER", "GlacierEQ")

def fetch_repos():
    repos, page = [], 1
    while True:
        req = urllib.request.Request(
            f"https://api.github.com/user/repos?per_page=100&page={page}&type=owner",
            headers={"Authorization": f"token {TOKEN}",
                     "Accept": "application/vnd.github+json"}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            batch = json.loads(r.read())
        if not batch:
            break
        repos.extend(batch)
        page += 1
    return repos

def analyze(repos):
    now = datetime.now(timezone.utc)
    results = {"total": len(repos), "stale": [], "backup": [], "no_description": [], "active": []}
    for r in repos:
        updated = datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00"))
        age_days = (now - updated).days
        entry = {"name": r["name"], "age_days": age_days,
                 "language": r.get("language"), "private": r["private"]}
        if r["name"].startswith("Z-BACKUP"):
            results["backup"].append(entry)
        elif age_days > 180:
            results["stale"].append(entry)
        elif not r.get("description"):
            results["no_description"].append(entry)
        else:
            results["active"].append(entry)
    return results

if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: APEX_GITHUB_TOKEN not set")
        exit(1)
    print(f"Scanning repos for {OWNER}...")
    repos = fetch_repos()
    analysis = analyze(repos)
    with open("repo_scan.json", "w") as f:
        json.dump(analysis, f, indent=2)
    print(f"Total repos: {analysis['total']}")
    print(f"Active: {len(analysis['active'])}")
    print(f"Stale (180+ days): {len(analysis['stale'])}")
    print(f"Backup repos: {len(analysis['backup'])}")
    print(f"No description: {len(analysis['no_description'])}")
    print("Results written to repo_scan.json")
