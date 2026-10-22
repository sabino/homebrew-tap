#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Propose only the cask verified by the read-only macOS update job."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from update_audifern import COMMIT, ROOT, current_cask, render, run, validate_transition

REPOSITORY = "sabino/homebrew-tap"
CASK = "Casks/audifern.rb"


def request(endpoint: str, data: dict | None = None):
    args = ["gh", "api", endpoint]
    if data is not None:
        args += ["--method", "POST", "--input", "-"]
    return json.loads(run(*args, **({"input": json.dumps(data)} if data is not None else {})))


def candidate_recipe(data: dict, before: str, base: str) -> str:
    if data.get("changed") is not True or not COMMIT.fullmatch(data.get("sourceCommit", "")):
        raise ValueError("Expected a changed, verified release candidate.")
    if data.get("baseCommit") != base or not COMMIT.fullmatch(base):
        raise ValueError("The prepared update is based on a different main commit.")
    if data.get("previousCaskSHA256") != hashlib.sha256(before.encode()).hexdigest():
        raise ValueError("The cask changed after verification.")
    version, digest = data["version"], data["sha256"]
    old_version, old_digest = current_cask(before)
    validate_transition(old_version, old_digest, version, digest)
    after = render(version, digest)
    if after == before:
        raise ValueError("The candidate contains no cask change.")
    return after


def main(candidate: Path) -> None:
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY or os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise ValueError("Only this repository's main workflow may publish cask updates.")
    data = json.loads(candidate.read_text())
    base = request(f"repos/{REPOSITORY}/git/ref/heads/main")["object"]["sha"]
    response = request(f"repos/{REPOSITORY}/contents/{CASK}?ref={base}")
    before = base64.b64decode(response["content"], validate=False).decode()
    after = candidate_recipe(data, before, base)
    branch = "updates/audifern-" + data["version"]
    ref = "refs/heads/" + branch
    existing = [r for r in request(f"repos/{REPOSITORY}/git/matching-refs/heads/{branch}") if r["ref"] == ref]
    if existing:
        tip = existing[0]["object"]["sha"]
        comparison = request(f"repos/{REPOSITORY}/compare/{base}...{tip}")
        committed = request(f"repos/{REPOSITORY}/commits/{tip}")
        stored = request(f"repos/{REPOSITORY}/contents/{CASK}?ref={tip}")
        if ([parent["sha"] for parent in committed["parents"]] != [base]
                or {f["filename"] for f in comparison.get("files", [])} != {CASK}
                or base64.b64decode(stored["content"]).decode() != after
                or committed["commit"]["verification"].get("verified") is not True):
            raise ValueError("An existing update branch differs from this candidate; review it manually.")
    else:
        request(f"repos/{REPOSITORY}/git/refs", {"ref": ref, "sha": base})
        # GitHub signs commits created by its commit API. Never export the
        # maintainer's personal GPG key into a workflow to impersonate them.
        query = """mutation($input:CreateCommitOnBranchInput!) {
          createCommitOnBranch(input:$input) {
            commit { oid signature { isValid wasSignedByGitHub } }
          }
        }"""
        result = request("graphql", {"query": query, "variables": {"input": {
            "branch": {"repositoryNameWithOwner": REPOSITORY, "branchName": branch},
            "expectedHeadOid": base,
            "message": {"headline": "Update Audifern to " + data["version"]},
            "fileChanges": {"additions": [{"path": CASK, "contents": base64.b64encode(after.encode()).decode()}]}
        }}})
        if result.get("errors"):
            raise ValueError("GitHub refused the cask commit.")
        signature = result["data"]["createCommitOnBranch"]["commit"].get("signature") or {}
        if signature.get("isValid") is not True or signature.get("wasSignedByGitHub") is not True:
            raise ValueError("The automated cask commit does not have GitHub's valid signature.")
    pulls = json.loads(run("gh", "pr", "list", "--repo", REPOSITORY, "--head", branch,
                           "--base", "main", "--state", "open", "--json", "number,url"))
    if not pulls:
        with tempfile.TemporaryDirectory(prefix="audifern-cask-pr-") as folder:
            body = Path(folder) / "body.txt"
            body.write_text(f"Install the verified Audifern {data['version']} release.\n\n"
                            f"Source: https://github.com/sabino/audifern/releases/tag/v{data['version']}\n\n"
                            "The read-only macOS job checked download hashes, the maintainer's signed tag, "
                            "source provenance, Developer ID signatures, stapled Apple tickets and Gatekeeper. "
                            "Homebrew also installed this exact candidate successfully.\n\n"
                            "Only `Casks/audifern.rb` changes. The automated commit is signed by GitHub; "
                            "this workflow has no Apple credentials or personal signing key.\n")
            run("gh", "pr", "create", "--repo", REPOSITORY, "--head", branch, "--base", "main",
                "--title", "Update Audifern to " + data["version"], "--body-file", str(body))
        pulls = json.loads(run("gh", "pr", "list", "--repo", REPOSITORY, "--head", branch,
                               "--base", "main", "--state", "open", "--json", "number,url"))
    if len(pulls) != 1:
        raise ValueError("Expected exactly one update pull request.")
    # GITHUB_TOKEN-created PRs do not trigger pull_request workflows. An
    # explicit dispatch runs the required checks on this exact branch.
    run("gh", "workflow", "run", "ci.yml", "--repo", REPOSITORY, "--ref", branch)
    run("gh", "pr", "merge", str(pulls[0]["number"]), "--repo", REPOSITORY,
        "--auto", "--squash", "--delete-branch")
    print("Update proposed; required checks gate automatic merge: " + pulls[0]["url"])


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError("Pass the verified candidate JSON path.")
        main(Path(sys.argv[1]))
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f"Cask publication stopped: {error}") from None
