#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Verify Audifern's public release before preparing a versioned cask."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "sabino/audifern"
TEAM = "79X9GDZ3WR"
SIGNER = "46AAE436358867E6A27E6C751BC0E4A3537E0BB8"
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")


def run(*args: str, timeout: int = 120, **kwargs) -> str:
    result = subprocess.run(args, check=False, text=True, capture_output=True,
                            timeout=timeout, **kwargs)
    if result.returncode:
        raise ValueError(f"{args[0]} failed ({result.returncode}): {result.stderr[-2000:].strip()}")
    return result.stdout


def api(endpoint: str) -> dict:
    return json.loads(run("gh", "api", endpoint))


def version_tuple(value: str) -> tuple[int, ...]:
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise ValueError("Expected a stable three-part version.")
    return tuple(int(part) for part in value.split("."))


def render(version: str, digest: str) -> str:
    version_tuple(version)
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        raise ValueError("Expected a pinned SHA-256 digest.")
    return f'''cask "audifern" do
  version "{version}"
  sha256 "{digest}"

  url "https://github.com/sabino/audifern/releases/download/v#{{version}}/Audifern-#{{version}}-macos-universal.dmg"
  name "Audifern"
  desc "Local Bluetooth controls for compatible hearing aids"
  homepage "https://github.com/sabino/audifern"

  livecheck do
    url :url
    strategy :github_latest
  end

  depends_on macos: :sonoma

  app "Audifern.app"
end
'''


def current_cask(text: str) -> tuple[str, str]:
    versions = re.findall(r'^  version "([^"\n]+)"$', text, re.MULTILINE)
    hashes = re.findall(r'^  sha256 "([0-9a-f]{64})"$', text, re.MULTILINE)
    if len(versions) != 1 or len(hashes) != 1:
        raise ValueError("The existing cask must have one version and one SHA-256.")
    version_tuple(versions[0])
    return versions[0], hashes[0]


def validate_release(release: dict) -> tuple[str, dict]:
    tag = release.get("tag_name", "")
    if not isinstance(tag, str) or not tag.startswith("v"):
        raise ValueError("Expected a stable version tag.")
    version = tag[1:]
    version_tuple(version)
    if release.get("draft") is not False or release.get("prerelease") is not False:
        raise ValueError("Only published stable releases can enter this tap.")
    if release.get("html_url") != f"https://github.com/{UPSTREAM}/releases/tag/{tag}":
        raise ValueError("Unexpected upstream release URL.")
    prefix = f"Audifern-{version}-macos-universal"
    names = {prefix + ".dmg", prefix + ".zip", "build-info.json", "SHA256SUMS"}
    assets = release.get("assets", [])
    by_name = {asset["name"]: asset for asset in assets}
    if len(assets) != len(names) or set(by_name) != names:
        raise ValueError("Expected exactly the four official release assets.")
    for name, asset in by_name.items():
        if asset.get("browser_download_url") != f"https://github.com/{UPSTREAM}/releases/download/{tag}/{name}":
            raise ValueError("A release asset points outside the expected versioned URL.")
        digest = asset.get("digest", "")
        if not isinstance(digest, str) or not digest.startswith("sha256:") or not SHA256.fullmatch(digest[7:]):
            raise ValueError("A release asset has no GitHub SHA-256 digest.")
        if asset.get("state") != "uploaded" or type(asset.get("size")) is not int or not 0 < asset["size"] < 128 * 1024 * 1024:
            raise ValueError("A release asset is incomplete or outside the size limit.")
    return version, by_name


def validate_manifest(data: dict, version: str) -> str:
    expected = {"application": "Audifern", "version": version, "releaseVersion": version,
                "sourceRepository": f"https://github.com/{UPSTREAM}", "minimumMacOS": "14.0",
                "architectures": ["arm64", "x86_64"], "signing": "developer-id", "notarized": True,
                "hardenedRuntime": True, "secureTimestamp": True, "teamID": TEAM}
    if any(type(data.get(key)) is not type(value) or data.get(key) != value for key, value in expected.items()):
        raise ValueError("Release provenance or notarization metadata differs from the expected policy.")
    commit = data.get("sourceCommit", "")
    if not isinstance(commit, str) or not COMMIT.fullmatch(commit):
        raise ValueError("The release source commit is missing.")
    return commit


def validate_transition(old_version: str, old_digest: str, version: str, digest: str) -> None:
    if version_tuple(version) < version_tuple(old_version):
        raise ValueError("Refusing to downgrade the tap to an older release.")
    if version == old_version and digest != old_digest:
        raise ValueError("A published version changed its download digest; refusing an immutable release replacement.")


def verify_tag(tag: str, commit: str, directory: Path) -> None:
    ref = api(f"repos/{UPSTREAM}/git/ref/tags/{tag}")
    if ref.get("object", {}).get("type") != "tag":
        raise ValueError("The release tag must be annotated and maintainer-signed.")
    signed = api(f"repos/{UPSTREAM}/git/tags/{ref['object']['sha']}")
    if signed.get("tag") != tag or signed.get("object") != {"sha": commit, "type": "commit", "url": f"https://api.github.com/repos/{UPSTREAM}/git/commits/{commit}"}:
        raise ValueError("The signed tag does not identify the manifested source commit.")
    signature = signed.get("verification", {})
    if signature.get("verified") is not True or signature.get("reason") != "valid":
        raise ValueError("GitHub did not verify the release tag signature.")
    sig = directory / "tag.asc"
    payload = directory / "tag.payload"
    sig.write_text(signature["signature"])
    payload.write_text(signature["payload"])
    gpg = shutil.which("gpg")
    if not gpg:
        raise ValueError("GnuPG is required to verify the maintainer's public release signature.")
    # macOS's default temporary path can exceed GnuPG's Unix socket limit.
    # This isolated home contains only the public verification key.
    with tempfile.TemporaryDirectory(prefix="af-gpg-", dir="/tmp") as home:
        try:
            run(gpg, "--batch", "--no-options", "--homedir", home, "--import", str(ROOT / ".github/audifern-release-key.asc"))
            status = run(gpg, "--batch", "--no-options", "--homedir", home, "--status-fd", "1",
                         "--verify", str(sig), str(payload))
            signatures = [line.split() for line in status.splitlines() if line.startswith("[GNUPG:] VALIDSIG ")]
            if len(signatures) != 1 or SIGNER not in {signatures[0][2], signatures[0][-1]}:
                raise ValueError("The release was not signed by the approved maintainer key.")
        finally:
            subprocess.run(["gpgconf", "--homedir", home, "--kill", "gpg-agent"], capture_output=True, check=False)
    comparison = api(f"repos/{UPSTREAM}/compare/{commit}...main")
    if comparison.get("status") not in {"identical", "ahead"} or comparison.get("base_commit", {}).get("sha") != commit:
        raise ValueError("The release source is not an ancestor of upstream main.")


def verify_ticket(path: Path) -> None:
    for attempt, delay in enumerate((0, 15, 30)):
        if delay:
            print(f"Retrying Apple's ticket service in {delay} seconds.", flush=True)
            time.sleep(delay)
        try:
            result = subprocess.run(["xcrun", "stapler", "validate", str(path)], capture_output=True, text=True, timeout=60)
            output = result.stdout + result.stderr
            if result.returncode == 0:
                return
            transient = result.returncode == 68 or "NSURLErrorDomain Code=-1005" in output
        except subprocess.TimeoutExpired:
            transient = True
        if not transient or attempt == 2:
            raise ValueError("Apple's stapled ticket validation did not pass.")


def verify_app(app: Path, version: str, commit: str | None = None) -> None:
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    if info.get("CFBundleIdentifier") != "org.audifern.app" or info.get("CFBundleShortVersionString") != version or info.get("LSMinimumSystemVersion") != "14.0":
        raise ValueError("Unexpected app identity, version or minimum macOS.")
    run("codesign", "--verify", "--deep", "--strict", str(app))
    for bundle, executable in ((app, "Audifern"), (app / "Contents/PlugIns/AudifernWidgets.appex", "AudifernWidgets")):
        details = subprocess.run(["codesign", "--display", "--verbose=4", str(bundle)], check=True, capture_output=True, text=True).stderr
        if f"TeamIdentifier={TEAM}\n" not in details or "Authority=Developer ID Application:" not in details or "(runtime)" not in details or "Timestamp=" not in details:
            raise ValueError("A bundle lacks the expected Developer ID, hardened runtime or secure timestamp.")
        if set(run("lipo", "-archs", str(bundle / f"Contents/MacOS/{executable}")).split()) != {"arm64", "x86_64"}:
            raise ValueError("The app and widget must be universal.")
    verify_ticket(app)
    run("spctl", "--assess", "--type", "execute", "--verbose=4", str(app))
    if commit and f"https://github.com/{UPSTREAM}/tree/{commit}" not in (app / "Contents/Resources/SOURCE.txt").read_text():
        raise ValueError("The app's bundled source notice differs from its manifest.")


def verify_dmg(path: Path, version: str, commit: str, directory: Path) -> None:
    run("hdiutil", "verify", "-quiet", str(path))
    run("codesign", "--verify", "--strict", str(path))
    verify_ticket(path)
    run("spctl", "--assess", "--type", "open", "--context", "context:primary-signature", "--verbose=4", str(path))
    mounted = directory / "mounted"
    mounted.mkdir()
    run("hdiutil", "attach", "-quiet", "-readonly", "-nobrowse", "-noautoopen", "-mountpoint", str(mounted), str(path))
    try:
        if (mounted / "Applications").readlink() != Path("/Applications"):
            raise ValueError("Unexpected DMG installation link.")
        verify_app(mounted / "Audifern.app", version, commit)
    finally:
        run("hdiutil", "detach", "-quiet", str(mounted))


def verify_downloads(version: str, assets: dict, directory: Path) -> str:
    for name, asset in assets.items():
        with urllib.request.urlopen(asset["browser_download_url"], timeout=60) as response:
            data = response.read(asset["size"] + 1)
        if len(data) != asset["size"] or "sha256:" + hashlib.sha256(data).hexdigest() != asset["digest"]:
            raise ValueError("A public download differs from GitHub's asset digest or size.")
        (directory / name).write_bytes(data)
    sums = {}
    for line in (directory / "SHA256SUMS").read_text().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._-]+)", line)
        if not match or match[2] in sums:
            raise ValueError("Invalid or duplicate checksum entry.")
        sums[match[2]] = match[1]
    if set(sums) != set(assets) - {"SHA256SUMS"} or any(sums[name] != assets[name]["digest"][7:] for name in sums):
        raise ValueError("The release checksum list differs from the public downloads.")
    return validate_manifest(json.loads((directory / "build-info.json").read_text()), version)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true", help="Verify the currently pinned release without editing files.")
    modes.add_argument("--probe", action="store_true", help="Check release metadata for an update without invoking macOS tools.")
    modes.add_argument("--candidate", type=Path, help="Prepare the latest verified stable release and write update metadata.")
    args = parser.parse_args()
    cask = ROOT / "Casks/audifern.rb"
    before = cask.read_text()
    old_version, old_digest = current_cask(before)
    endpoint = f"repos/{UPSTREAM}/releases/" + (f"tags/v{old_version}" if args.check else "latest")
    version, assets = validate_release(api(endpoint))
    digest = assets[f"Audifern-{version}-macos-universal.dmg"]["digest"][7:]
    validate_transition(old_version, old_digest, version, digest)
    after = render(version, digest)
    changed = before != after
    if args.probe:
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as output:
                output.write(f"changed={str(changed).lower()}\nversion={version}\n")
        print(f"Audifern {version}: " + ("an update needs verification." if changed else "cask is current."))
        return
    with tempfile.TemporaryDirectory(prefix="audifern-cask-verify-") as folder:
        directory = Path(folder)
        commit = verify_downloads(version, assets, directory)
        verify_tag("v" + version, commit, directory)
        verify_dmg(directory / f"Audifern-{version}-macos-universal.dmg", version, commit, directory)
    if args.check and changed:
        raise ValueError("The checked-in cask differs from the verified canonical release recipe.")
    if args.candidate:
        candidate = {"version": version, "sha256": digest, "sourceCommit": commit,
                     "previousCaskSHA256": hashlib.sha256(before.encode()).hexdigest(),
                     "baseCommit": run("git", "-C", str(ROOT), "rev-parse", "HEAD").strip(), "changed": changed}
        args.candidate.write_text(json.dumps(candidate, indent=2) + "\n")
        if changed:
            cask.write_text(after)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(f"changed={str(changed).lower()}\nversion={version}\n")
    print(f"Verified Audifern {version}: release hashes, maintainer signature, Developer ID, Apple tickets and Gatekeeper.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f"Cask verification failed: {error}") from None
