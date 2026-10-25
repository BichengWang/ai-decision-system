"""Outreach trigger behavior, with PyPI and GitHub replaced by in-memory fakes."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parents[1] / "outreach.py"
SPEC = importlib.util.spec_from_file_location("outreach", MODULE_PATH)
outreach = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(outreach)

PUBLISHER = {"kind": "GitHub", "repository": "owner/repo", "workflow": "release.yml"}
POST = "## Post\n\n````text\nOut now:\n\n{{releases}}\n\n```text\n{{demo}}\n```\n\n{{demo_note}}\n````\n"


def attested(*names, publisher=PUBLISHER, yanked=False):
    return {"url": "https://pypi.org/project/pkg/1.0.0/",
            "files": [{"filename": name, "yanked": yanked, "publishers": [dict(publisher)]} for name in names]}


class FakeGitHub:
    repo = "owner/repo"

    def __init__(self, releases=None):
        self.release_map = releases if releases is not None else {
            "pkg/v1.0.0": {"draft": False, "published_at": "2026-12-10T00:00:00Z", "html_url": "https://gh/rel"}}
        self.issue_map, self.created, self.edited, self.comments, self.posted = {}, [], [], [], []
        self.titles = {}
        self.discussions_calls = 0

    def releases(self):
        return self.release_map

    def issues(self):
        return {outreach.MARKER_RE.search(issue["body"]).group(1): issue for issue in self.issue_map.values()}

    def create_issue(self, title, body):
        number = 10 + len(self.created)
        self.created.append(title)
        self.issue_map[number] = {"number": number, "body": body}
        return {"html_url": f"https://gh/issues/{number}"}

    def edit_issue(self, number, body):
        self.edited.append(number)
        self.issue_map[number]["body"] = body

    def comment(self, number, body):
        self.comments.append((number, body))

    def discussions(self):
        self.discussions_calls += 1
        return {"id": "R1", "discussionCategories": {"nodes": [{"id": "C1", "name": "Announcements"}]},
                "discussions": {"nodes": [{"title": title, "url": url} for title, url in self.titles.items()]}}

    def create_discussion(self, repository_id, category_id, title, body):
        self.posted.append((repository_id, category_id, title, body))
        self.titles[title] = "https://gh/discussions/1"
        return "https://gh/discussions/1"


class OutreachTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "docs/launch").mkdir(parents=True)
        (self.root / "docs/launch/announce.md").write_text(POST)
        self.flag = self.root / "demo-passes"
        self.flag.touch()
        self.milestone = {
            "title": "pkg 1.0.0 is on PyPI",
            "requires": [{"pypi": "pkg", "version": "1.0.0"}, {"github_release": "pkg/v1.0.0"}],
            "demo": [{"run": "echo installed"}, {"run": f"test -f '{self.flag}' && echo 'exit code: 1'",
                                                 "expect": ["exit code: 1"]}],
            "announcement": {"title": "pkg 1.0.0", "draft": "docs/launch/announce.md"},
            "channels": [{"venue": "LinkedIn", "by": "owner posts", "draft": "docs/launch/announce.md"}],
        }
        self.write_manifest()

    def write_manifest(self):
        (self.root / outreach.MANIFEST).write_text(json.dumps(
            {"schema_version": 1, "publisher": PUBLISHER, "milestones": {"pkg-1.0.0": self.milestone}}))

    def start(self, github, pypi=lambda dist, version: attested("pkg-1.0.0.tar.gz", "pkg-1.0.0-py3-none-any.whl")):
        with mock.patch("sys.stdout"):
            return outreach.start(self.root, github, pypi, "2026-12-10")

    def test_reached_only_when_every_file_has_provenance_from_the_manifest_publisher(self):
        missing = lambda pypi, releases=FakeGitHub().release_map: outreach.check(
            self.milestone, PUBLISHER, pypi, releases)[1]
        self.assertEqual(missing(lambda d, v: attested("a.whl", "b.tar.gz")), [])
        self.assertEqual(missing(lambda d, v: None), ["pkg 1.0.0 on PyPI: not published"])
        other = dict(PUBLISHER, repository="someone/fork")
        file = attested("a.whl")["files"][0]
        forked = {"url": "u", "files": [file, dict(file, filename="b.tar.gz", publishers=[other])]}
        self.assertIn("b.tar.gz has no provenance", missing(lambda d, v: forked)[0])
        self.assertNotIn("a.whl", missing(lambda d, v: forked)[0])
        self.assertIn("is yanked", missing(lambda d, v: attested("a.whl", yanked=True))[0])
        self.assertIn("no files", missing(lambda d, v: {"url": "u", "files": []})[0])
        draft = {"pkg/v1.0.0": {"draft": True}}
        self.assertEqual(missing(lambda d, v: attested("a.whl"), draft), ["GitHub Release pkg/v1.0.0: draft"])
        self.assertEqual(missing(lambda d, v: attested("a.whl"), {}), ["GitHub Release pkg/v1.0.0: not published"])

    def test_not_reached_writes_nothing(self):
        github = FakeGitHub(releases={})
        self.assertEqual(self.start(github), [])
        self.assertEqual(github.created, [])

    def test_reached_milestone_opens_exactly_one_issue_and_announces_once(self):
        github = FakeGitHub()
        self.assertEqual(self.start(github), ["pkg-1.0.0"])
        self.assertEqual(github.created, ["Outreach: pkg 1.0.0 is on PyPI"])
        body = github.issue_map[10]["body"]
        self.assertNotIn(outreach.BLOCKED, body)
        announcement = outreach.extract_announcement(body)
        self.assertIn("- [pkg 1.0.0 on PyPI](https://pypi.org/project/pkg/1.0.0/)", announcement)
        self.assertIn("$ echo installed\ninstalled\n$ test -f", announcement)
        self.assertNotIn("{{", announcement)

        self.assertEqual(self.start(github), ["pkg-1.0.0"])
        self.assertEqual((len(github.created), github.edited), (1, []))

        # The owner rewrites the text in the issue; GitHub stores edited bodies with CRLF.
        edited = body.replace(announcement, "Rewritten by the owner.\nSecond line.").replace("\n", "\r\n")
        github.issue_map[10]["body"] = edited
        with mock.patch("sys.stdout"):
            outreach.announce(self.root, github, ["pkg-1.0.0"])
            outreach.announce(self.root, github, ["pkg-1.0.0"])
        self.assertEqual(github.posted, [("R1", "C1", "pkg 1.0.0", "Rewritten by the owner.\nSecond line.")])
        self.assertEqual(github.comments, [(10, "Announced in GitHub Discussions: https://gh/discussions/1")])

    def test_announce_enabled_after_issue_creation(self):
        github = FakeGitHub()
        # The workflow skips announce while OUTREACH_ANNOUNCE is disabled.
        self.assertEqual(self.start(github), ["pkg-1.0.0"])
        self.assertEqual(github.posted, [])

        # Once enabled, it forwards the next start's output to announce.
        with mock.patch("sys.stdout"):
            outreach.announce(self.root, github, self.start(github))
        self.assertEqual(len(github.posted), 1)
        self.assertEqual((len(github.created), github.edited), (1, []))

    def test_failed_announcement_retries_on_later_start(self):
        github = FakeGitHub()
        ready = self.start(github)
        with mock.patch.object(github, "create_discussion", side_effect=outreach.Blocked("posting failed")):
            with self.assertRaisesRegex(outreach.Blocked, "posting failed"):
                outreach.announce(self.root, github, ready)
        self.assertEqual(github.comments, [])

        with mock.patch("sys.stdout"):
            outreach.announce(self.root, github, self.start(github))
            outreach.announce(self.root, github, self.start(github))
        self.assertEqual(len(github.posted), 1)
        self.assertEqual(len(github.comments), 1)

    def test_existing_issue_is_not_ready_when_requirements_no_longer_hold(self):
        github = FakeGitHub()
        self.start(github)
        body = github.issue_map[10]["body"]
        self.assertEqual(self.start(github, pypi=lambda dist, version: None), [])
        github.release_map = {}
        self.assertEqual(self.start(github), [])
        self.assertEqual(github.issue_map[10]["body"], body)
        self.assertEqual(github.edited, [])

    def test_existing_issue_without_an_announcement_is_not_ready(self):
        del self.milestone["announcement"]
        self.write_manifest()
        github = FakeGitHub()
        self.assertEqual(self.start(github), [])
        self.assertEqual(self.start(github), [])
        self.assertEqual((len(github.created), github.edited), (1, []))
        self.assertEqual(github.discussions_calls, 0)

    def test_existing_issues_only_offer_unposted_titles_with_one_discussions_fetch(self):
        manifest = json.loads((self.root / outreach.MANIFEST).read_text())
        manifest["milestones"]["pkg-followup"] = dict(
            self.milestone, announcement=dict(self.milestone["announcement"], title="pkg followup"))
        (self.root / outreach.MANIFEST).write_text(json.dumps(manifest))
        github = FakeGitHub()
        self.assertEqual(self.start(github), ["pkg-1.0.0", "pkg-followup"])
        self.assertEqual(github.discussions_calls, 0)

        for titles, expected in [
            ([], ["pkg-1.0.0", "pkg-followup"]),
            (["pkg 1.0.0"], ["pkg-followup"]),
            (["pkg 1.0.0", "pkg followup"], []),
        ]:
            with self.subTest(posted=titles):
                github.titles = dict.fromkeys(titles, "https://gh/discussions/posted")
                github.discussions_calls = 0
                self.assertEqual(self.start(github), expected)
                self.assertEqual(github.discussions_calls, 1)
        self.assertEqual((len(github.created), github.edited), (2, []))

    def test_new_issue_is_ready_without_checking_posted_titles(self):
        github = FakeGitHub()
        github.titles["pkg 1.0.0"] = "https://gh/discussions/posted"
        self.assertEqual(self.start(github), ["pkg-1.0.0"])
        self.assertEqual(github.discussions_calls, 0)
        with mock.patch("sys.stdout"):
            outreach.announce(self.root, github, ["pkg-1.0.0"])
        self.assertEqual(github.posted, [])

    def test_later_start_preserves_owner_edited_issue(self):
        github = FakeGitHub()
        self.start(github)
        body = github.issue_map[10]["body"]
        edited = body.replace(outreach.extract_announcement(body), "Owner's announcement.")
        edited = edited.replace("- [ ] **LinkedIn**", "- [x] **LinkedIn**").replace("\n", "\r\n")
        github.issue_map[10]["body"] = edited

        with mock.patch.object(outreach, "run_demo") as demo:
            self.assertEqual(self.start(github), ["pkg-1.0.0"])
        demo.assert_not_called()
        self.assertEqual(github.issue_map[10]["body"], edited)
        self.assertEqual(github.edited, [])
        with mock.patch("sys.stdout"):
            outreach.announce(self.root, github, self.start(github))
        self.assertEqual(github.posted[0][3], "Owner's announcement.")

    def test_announcement_on_second_discussions_page_is_not_reposted(self):
        github = FakeGitHub()
        ready = self.start(github)
        repository = {"id": "R1", "discussionCategories": {"nodes": [{"id": "C1", "name": "Announcements"}]}}
        pages = [
            {"data": {"repository": dict(repository, discussions={
                "nodes": [{"title": f"Other {number}", "url": f"https://gh/discussions/{number}"}
                          for number in range(100)],
                "pageInfo": {"hasNextPage": True, "endCursor": "page-one-end"}})}},
            {"data": {"repository": dict(repository, discussions={
                "nodes": [{"title": "pkg 1.0.0", "url": "https://gh/discussions/older"}],
                "pageInfo": {"hasNextPage": False, "endCursor": "page-two-end"}})}},
        ]
        with mock.patch.object(github, "discussions", lambda: outreach.GitHub.discussions(github)), \
                mock.patch.object(outreach, "run", side_effect=[json.dumps(page) for page in pages]) as run, \
                mock.patch("sys.stdout"):
            outreach.announce(self.root, github, ready)
        self.assertEqual(github.posted, [])
        self.assertEqual(github.comments, [])
        self.assertEqual(run.call_count, 2)
        payloads = [json.loads(call.kwargs["input_text"]) for call in run.call_args_list]
        self.assertIsNone(payloads[0]["variables"].get("after"))
        self.assertEqual(payloads[1]["variables"]["after"], "page-one-end")
        self.assertIn("after: $after", payloads[0]["query"])
        self.assertIn("pageInfo", payloads[0]["query"])

    def test_failed_demo_blocks_announcement_until_a_later_run_reproduces(self):
        self.flag.unlink()
        github = FakeGitHub()
        self.assertEqual(self.start(github), [])
        body = github.issue_map[10]["body"]
        self.assertIn(outreach.BLOCKED, body)
        self.assertIn("exited 1", body)
        self.assertIsNone(outreach.extract_announcement(body))
        with self.assertRaisesRegex(outreach.Blocked, "has not reproduced"):
            outreach.announce(self.root, github, ["pkg-1.0.0"])

        self.flag.touch()
        self.assertEqual(self.start(github), ["pkg-1.0.0"])
        self.assertEqual((len(github.created), github.edited), (1, [10]))
        self.assertNotIn(outreach.BLOCKED, github.issue_map[10]["body"])

    def test_demo_stops_at_the_first_unmet_expectation_and_gets_no_token(self):
        steps = [{"run": 'echo "token=${GH_TOKEN:-unset}"', "expect": ["token=unset"]},
                 {"run": "echo found", "expect": ["found", "missing"]},
                 {"run": "echo never"}]
        with tempfile.TemporaryDirectory() as workdir, mock.patch.dict(os.environ, {"GH_TOKEN": "secret"}):
            transcript, problem = outreach.run_demo(steps, workdir)
        self.assertIn("did not print ['missing']", problem)
        self.assertEqual(transcript, '$ echo "token=${GH_TOKEN:-unset}"\ntoken=unset\n$ echo found\nfound')

    def test_manifest_problems_are_all_reported(self):
        self.milestone["channels"].append({"venue": "Medium", "by": "owner", "draft": "docs/launch/medium.md"})
        self.milestone["requires"].append({"pypi": "pkg"})
        self.write_manifest()
        (self.root / "docs/launch/announce.md").write_text(POST.replace("{{demo}}", "{{transcript}}"))
        with self.assertRaises(outreach.Blocked) as caught:
            outreach.load(self.root)
        message = str(caught.exception)
        self.assertIn("docs/launch/medium.md does not exist", message)
        self.assertIn("must have pypi and version", message)
        self.assertIn("unknown placeholders ['transcript']", message)

    def test_shipped_manifest_is_valid(self):
        manifest = outreach.load()
        self.assertTrue(manifest["milestones"])


if __name__ == "__main__":
    unittest.main()
