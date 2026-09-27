import importlib.util
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo


MODULE_PATH = Path(__file__).resolve().parents[1] / "continual_delivery.py"
SPEC = importlib.util.spec_from_file_location("continual_delivery", MODULE_PATH)
delivery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(delivery)


SHA = "a" * 40


def pr(**changes):
    result = {
        "state": "OPEN", "isDraft": False, "baseRefName": "main",
        "headRefName": "codex/issue-42", "headRefOid": SHA,
        "mergeStateStatus": "CLEAN", "body": "Closes #42\n\nImplementation run: implement-42",
        "labels": [{"name": delivery.MANAGED}],
        "files": [{"path": "src/utils/general/example.py"}],
        "statusCheckRollup": [{"name": "Delivery policy", "conclusion": "SUCCESS", "workflowName": "Delivery policy"}],
    }
    result.update(changes)
    return result


def receipt(sha=SHA, verdict="PASS", findings=0):
    data = {
        "head_sha": sha, "verdict": verdict,
        "blocking_findings": findings, "reviewer_run": "separate-review-1",
    }
    return {"body": f"{delivery.REVIEW_PREFIX}{json.dumps(data)} -->"}


class EvaluationTests(unittest.TestCase):
    def test_valid_review_and_ci_pass(self):
        self.assertEqual(delivery.evaluate(pr(), [receipt()], []), [])

    def test_new_head_invalidates_review(self):
        failures = delivery.evaluate(pr(headRefOid="b" * 40), [receipt()], [])
        self.assertTrue(any("review" in item for item in failures))

    def test_later_blocking_review_wins(self):
        failures = delivery.evaluate(pr(), [receipt(), receipt(verdict="BLOCK", findings=1)], [])
        self.assertTrue(any("review" in item for item in failures))

    def test_self_review_receipt_does_not_pass(self):
        self.assertTrue(delivery.evaluate(pr(), [receipt()], []) == [])
        own = receipt()
        own["body"] = own["body"].replace("separate-review-1", "implement-42")
        self.assertTrue(any("review" in item for item in delivery.evaluate(pr(), [own], [])))

    def test_failed_and_missing_checks_block(self):
        self.assertTrue(delivery.evaluate(pr(statusCheckRollup=[]), [receipt()], []))
        failed = pr(statusCheckRollup=[{"name": "Delivery policy", "conclusion": "FAILURE"}])
        self.assertTrue(delivery.evaluate(failed, [receipt()], []))

    def test_duplicate_or_wrong_workflow_check_blocks(self):
        good = {"name": "Delivery policy", "conclusion": "SUCCESS", "workflowName": "Delivery policy"}
        bad = {"name": "Delivery policy", "conclusion": "FAILURE", "workflowName": "Delivery policy"}
        wrong = {"name": "Delivery policy", "conclusion": "SUCCESS", "workflowName": "untrusted"}
        self.assertTrue(delivery.evaluate(pr(statusCheckRollup=[good, bad]), [receipt()], []))
        self.assertTrue(delivery.evaluate(pr(statusCheckRollup=[wrong]), [receipt()], []))

    def test_merge_conflict_and_behind_block(self):
        for state in ("DIRTY", "BEHIND", "BLOCKED", "UNKNOWN"):
            with self.subTest(state=state):
                self.assertTrue(delivery.evaluate(pr(mergeStateStatus=state), [receipt()], []))

    def test_release_related_diff_blocks(self):
        changed = pr(files=[{"path": "docs/RELIA_RELEASE.md"}])
        self.assertTrue(any("release" in item for item in delivery.evaluate(changed, [receipt()], [])))

    def test_area_checks_required(self):
        changed = pr(files=[{"path": "ai-workflows/experiment-gate/expgate/run.py"}])
        failures = delivery.evaluate(changed, [receipt()], [])
        self.assertTrue(any("test (3.11)" in item for item in failures))
        self.assertTrue(any("test (3.13)" in item for item in failures))

    def test_attribution_rule(self):
        changed = pr(body="Co-authored-by: Codex")
        failures = delivery.evaluate(changed, [receipt()], [])
        self.assertTrue(any("description" in item for item in failures))
        commit = {"commit": {"author": {"name": "Codex", "email": "x@y"}, "message": "change"}}
        self.assertTrue(any("author" in item for item in delivery.evaluate(pr(), [receipt()], [commit])))

    def test_daily_cap_uses_los_angeles_date(self):
        now = datetime(2026, 9, 26, 0, 20, tzinfo=ZoneInfo("America/Los_Angeles"))
        merged = [
            {"labels": [{"name": delivery.MANAGED}], "mergedAt": "2026-09-26T06:00:00Z"},
            {"labels": [{"name": delivery.MANAGED}], "mergedAt": "2026-09-26T07:01:00Z"},
        ]
        self.assertEqual(delivery.day_counts(merged, now), 1)

    def test_snapshot_reconciles_active_issue_and_three_pr_limit(self):
        prs = [
            {"number": i, "title": "x", "headRefName": f"codex/issue-{i}",
             "labels": [{"name": delivery.MANAGED}], "url": "https://example.test"}
            for i in (1, 2, 3)
        ]
        issues = [
            {"number": i, "title": "x", "createdAt": "2026-09-26T00:00:00Z",
             "labels": [{"name": delivery.READY}], "url": "https://example.test"}
            for i in (1, 4)
        ]
        with patch.object(delivery, "run"), patch.object(delivery, "repo_name", return_value="a/b"), \
             patch.object(delivery, "gh_json", side_effect=[prs, [], issues]):
            result = delivery.snapshot()
        self.assertIsNone(result["next_issue"])
        self.assertEqual(result["blocker"], "three PRs open")

    def test_stale_review_cannot_be_recorded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            path.write_text(json.dumps({
                "head_sha": "b" * 40, "verdict": "PASS", "blocking_findings": 0,
                "reviewer_run": "other-task",
            }))
            with patch.object(delivery, "gh_json", return_value={"headRefOid": SHA}):
                with self.assertRaises(delivery.Blocked):
                    delivery.record_review("a/b", 42, path)

    def test_merge_blocks_at_daily_cap_before_network_mutation(self):
        with patch.object(delivery, "snapshot", return_value={"merged_today": 20}), \
             patch.object(delivery, "run") as command:
            with self.assertRaises(delivery.Blocked):
                delivery.merge("a/b", 42)
            command.assert_not_called()

    def test_merge_lock_blocks_overlapping_runs(self):
        with delivery.merge_lock("a/b"):
            with self.assertRaises(delivery.Blocked):
                with delivery.merge_lock("a/b"):
                    pass

    def test_unprotected_main_blocks_merge_gate(self):
        with patch.object(delivery, "gh_json", return_value={
            "required_status_checks": {"contexts": ["Delivery policy", "RELIA required"], "strict": True},
            "enforce_admins": {"enabled": False},
        }):
            with self.assertRaises(delivery.Blocked):
                delivery.branch_rules("a/b")

    def test_unavailable_github_blocks_snapshot(self):
        with patch.object(delivery, "run", side_effect=delivery.Blocked("auth unavailable")):
            with self.assertRaises(delivery.Blocked):
                delivery.snapshot()


if __name__ == "__main__":
    unittest.main()
