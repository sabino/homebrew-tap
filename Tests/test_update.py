# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from update_audifern import (TEAM, current_cask, render, validate_manifest,
                             validate_release, validate_transition, verify_ticket, version_tuple)
from publish_update import candidate_recipe


def release():
    version = "0.8.1"
    names = [f"Audifern-{version}-macos-universal.{ext}" for ext in ("dmg", "zip")] + ["build-info.json", "SHA256SUMS"]
    return {"tag_name": "v" + version, "draft": False, "prerelease": False,
            "html_url": "https://github.com/sabino/audifern/releases/tag/v" + version,
            "assets": [{"name": name, "digest": "sha256:" + "a" * 64, "state": "uploaded", "size": 10,
                        "browser_download_url": f"https://github.com/sabino/audifern/releases/download/v{version}/{name}"} for name in names]}


def manifest():
    return {"application": "Audifern", "version": "0.8.1", "releaseVersion": "0.8.1",
            "sourceRepository": "https://github.com/sabino/audifern", "minimumMacOS": "14.0",
            "architectures": ["arm64", "x86_64"], "signing": "developer-id", "notarized": True,
            "hardenedRuntime": True, "secureTimestamp": True, "teamID": TEAM, "sourceCommit": "b" * 40}


class ReleasePolicyTests(unittest.TestCase):
    def test_stable_official_release(self):
        version, assets = validate_release(release())
        self.assertEqual(version, "0.8.1")
        self.assertEqual(len(assets), 4)

    def test_rejects_unpublished_prerelease_or_invalid_versions(self):
        for change in ({"draft": True}, {"prerelease": True}, {"tag_name": "v0.8.1-beta"},
                       {"tag_name": "v01.2.3"}, {"tag_name": "v0.8.1\n"}, {"draft": 0}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_release({**release(), **change})

    def test_rejects_retargeted_release(self):
        data = release()
        data["html_url"] = "https://github.com/other/audifern/releases/tag/v0.8.1"
        with self.assertRaises(ValueError):
            validate_release(data)

    def test_rejects_duplicate_missing_or_additional_assets(self):
        for mode in ("duplicate", "missing", "additional"):
            data = release()
            if mode == "duplicate":
                data["assets"][-1] = deepcopy(data["assets"][0])
            elif mode == "missing":
                data["assets"].pop()
            else:
                data["assets"].append({"name": "unreviewed.pkg"})
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                validate_release(data)

    def test_rejects_unpinned_external_or_incomplete_assets(self):
        for change in ({"digest": "sha256:" + "a" * 63}, {"digest": "sha256:" + "A" * 64},
                       {"browser_download_url": "https://example.com/app.dmg"}, {"size": True},
                       {"size": 128 * 1024 * 1024}, {"state": "uploading"}):
            data = release()
            data["assets"][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_release(data)

    def test_requires_all_security_and_provenance_claims(self):
        self.assertEqual(validate_manifest(manifest(), "0.8.1"), "b" * 40)
        changes = {"signing": "ad-hoc", "notarized": False, "teamID": "OTHERTEAM1",
                   "architectures": ["arm64"], "hardenedRuntime": False, "secureTimestamp": False,
                   "sourceRepository": "https://example.com", "sourceCommit": "not-a-commit",
                   "version": "0.8.0", "minimumMacOS": "15.0"}
        for key, value in changes.items():
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_manifest({**manifest(), key: value}, "0.8.1")
        with self.assertRaises(ValueError):
            validate_manifest({**manifest(), "notarized": 1}, "0.8.1")


class CandidatePolicyTests(unittest.TestCase):
    def test_numeric_order_and_immutable_release(self):
        self.assertGreater(version_tuple("0.10.0"), version_tuple("0.9.9"))
        validate_transition("0.8.0", "a" * 64, "0.8.1", "b" * 64)
        with self.assertRaises(ValueError):
            validate_transition("0.8.1", "a" * 64, "0.8.0", "b" * 64)
        with self.assertRaises(ValueError):
            validate_transition("0.8.1", "a" * 64, "0.8.1", "b" * 64)

    def test_recipe_inputs_cannot_inject_ruby(self):
        for version, digest in (("0.8.1\"\nsystem 'bad'", "a" * 64), ("0.8.1", "a" * 64 + "\n"), ("../1", "a" * 64)):
            with self.subTest(version=version), self.assertRaises(ValueError):
                render(version, digest)

    def test_ambiguous_cask_metadata_is_refused(self):
        with self.assertRaises(ValueError):
            current_cask(render("0.8.0", "a" * 64) + '  version "0.8.1"\n')

    def test_publisher_reconstructs_only_a_verified_candidate(self):
        before = render("0.8.0", "a" * 64)
        data = {"version": "0.8.1", "sha256": "b" * 64, "sourceCommit": "c" * 40,
                "previousCaskSHA256": hashlib.sha256(before.encode()).hexdigest(),
                "baseCommit": "d" * 40, "changed": True}
        self.assertEqual(candidate_recipe(data, before, "d" * 40), render("0.8.1", "b" * 64))
        for key, value in (("baseCommit", "e" * 40), ("previousCaskSHA256", "f" * 64),
                           ("sourceCommit", "unverified"), ("changed", False), ("version", "0.7.0")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                candidate_recipe({**data, key: value}, before, "d" * 40)


class AppleTicketPolicyTests(unittest.TestCase):
    @patch("update_audifern.time.sleep")
    @patch("update_audifern.subprocess.run")
    def test_invalid_tickets_fail_without_retry(self, command, sleep):
        command.return_value = Mock(returncode=65, stdout="Invalid ticket.", stderr="")
        with self.assertRaises(ValueError):
            verify_ticket(Path("Audifern.app"))
        self.assertEqual(command.call_count, 1)
        sleep.assert_not_called()

    @patch("update_audifern.time.sleep")
    @patch("update_audifern.subprocess.run")
    def test_network_failure_is_retried_but_still_requires_success(self, command, sleep):
        command.side_effect = [Mock(returncode=65, stdout="NSURLErrorDomain Code=-1005", stderr=""),
                               Mock(returncode=0, stdout="Validated.", stderr="")]
        verify_ticket(Path("Audifern.app"))
        self.assertEqual(command.call_count, 2)

    @patch("update_audifern.time.sleep")
    @patch("update_audifern.subprocess.run")
    def test_persistent_service_failure_stops_publication(self, command, sleep):
        command.return_value = Mock(returncode=68, stdout="Service unavailable.", stderr="")
        with self.assertRaises(ValueError):
            verify_ticket(Path("Audifern.app"))
        self.assertEqual(command.call_count, 3)


if __name__ == "__main__":
    unittest.main()
