"""개인 설정 `check_scope = "shared"` 면 쓰는 순간의 검사가 공유·배포 문서만 본다(2026-11-04 작성자 결정).

**왜.** 작성자에게만 보여 주는 결정 모음, 시안, 작업 메모까지 쓸 때마다 검사기가 돌아 지적이 붙었다.
작성자 말로 「나한테만 보여주는 건 한글 검사기 안 돌리도록. 배포나 공유 목적으로 작성할 때에만」.

**기본값은 그대로다** — 설정이 없으면 예전처럼 전부 본다. 이 훅을 설치한 다른 사람의 검사가 조용히 꺼지면 안 된다.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

HOOK = repo_paths.hook("doc-style-gate.py")


def load(publish_file):
    # 앞 값을 되돌린다 — 지우면 시험 실행기가 막아 둔 개인 목록을 뒤 시험이 다시 읽는다(scripts/run_tests.py)
    before = os.environ.get("KOREAN_QA_PUBLISH_REPOS")
    os.environ["KOREAN_QA_PUBLISH_REPOS"] = str(publish_file)
    try:
        spec = importlib.util.spec_from_file_location("gate_scope", HOOK)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        if before is None:
            os.environ.pop("KOREAN_QA_PUBLISH_REPOS", None)
        else:
            os.environ["KOREAN_QA_PUBLISH_REPOS"] = before
    return mod


class CheckScope(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        (self.repo / "docs").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "remote", "add", "origin",
                        "https://github.com/example/shared-docs.git"], check=True)
        self.shared = self.repo / "docs" / "guide.md"
        self.draft = self.repo / "notes.md"
        self.loose = self.root / "desk.html"
        for p in (self.shared, self.draft, self.loose):
            p.write_text("# 제목\n\n본문입니다.\n", encoding="utf-8")
        self.listing = self.root / "local-publish-repos.toml"

    def tearDown(self):
        self.tmp.cleanup()

    def write_listing(self, scope):
        head = f'check_scope = "{scope}"\n\n' if scope else ""
        self.listing.write_text(head + '[[repo]]\norigin = "github.com/example/shared-docs"\n'
                                'targets = ["docs/*.md"]\n', encoding="utf-8")

    def test_without_setting_everything_is_checked(self):
        self.write_listing(None)
        gate = load(self.listing)
        self.assertEqual([gate.audience(p) for p in (self.shared, self.draft, self.loose)], [None, None, None])

    def test_shared_scope_separates_publish_targets(self):
        self.write_listing("shared")
        gate = load(self.listing)
        self.assertEqual(gate.audience(self.shared), "share")
        self.assertEqual(gate.audience(self.draft), "me")      # 발행 무늬 밖
        self.assertEqual(gate.audience(self.loose), "me")      # 저장소 밖

    def test_document_marker_wins(self):
        self.write_listing("shared")
        self.loose.write_text('<meta name="audience" content="share">\n<p>공지</p>\n', encoding="utf-8")
        self.shared.write_text("---\naudience: me\n---\n# 초안\n", encoding="utf-8")
        gate = load(self.listing)
        self.assertEqual(gate.audience(self.loose), "share")
        self.assertEqual(gate.audience(self.shared), "me")

    def test_write_hook_is_silent_for_my_documents(self):
        self.write_listing("shared")
        gate = load(self.listing)
        self.loose.write_text("<h1>결정 모음</h1>\n<ul><li>이 값은 서술형이다.</li></ul>\n", encoding="utf-8")
        payload = {"hook_event_name": "PostToolUse", "tool_name": "Write", "session_id": "t",
                   "tool_input": {"file_path": str(self.loose)}}
        ran = []
        # 임시 폴더는 훅이 원래 빼므로 대상 찾기는 바꿔 끼우고, 검사기가 불리는지만 본다
        gate.targets = lambda _p: ([str(self.loose), str(self.shared)], True, "once")
        gate.korean_targets = lambda _p: [str(self.loose)]
        gate.run_checker = lambda fp, _e: ran.append(fp) or ""
        gate.run_korean_checker = lambda fp: ran.append(fp) or ""
        gate.middot_report = lambda _fp: []
        gate.note_pass = lambda *a: None
        gate.load = lambda: {}
        gate.save = lambda _s: None
        gate.publish_block = lambda *_a: ""
        gate._main(payload)
        self.assertEqual(ran, [str(self.shared)])          # 내 문서는 안 부르고 공유 문서만


if __name__ == "__main__":
    unittest.main()
