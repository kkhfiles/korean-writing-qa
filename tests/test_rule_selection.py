"""갈래를 끄고 낮추는 설정이 실제로 듣는지, 그리고 끈 것이 드러나는지 지킨다.

**왜 넣었나.** 조직마다 문서 관행이 다르다. 표 머리 「비고」는 공문서 표준 관례라
그 조직에서는 지적이 아니고, 발표 대본은 산문이 정상이다. 남이 받아 쓰려면 갈래를
고를 수 있어야 한다.

**같이 들어오는 실패.** 갈래를 조용히 끄면 「오류 0」이 통과인지 안 본 것인지
갈리지 않는다. 이 검사기가 자기에게서 배운 「검사 불가는 합격이 아니라 안 본 것」이
설정에도 그대로 걸린다. 그래서 세 가지를 함께 못 박는다.

1. 목록이 검사기가 내는 갈래를 **빠짐없이** 덮는다 — 빠지면 그 갈래는 끌 수가 없다
2. 끄기·낮추기·올리기가 실제로 판정을 바꾼다
3. **껐다는 사실이 출력 맨 위와 합계 두 곳에 적힌다**
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

CHECKER = repo_paths.CHECKER

# 갈래 다섯이 한 번에 나는 문서 — 끄기 전후를 비교할 표본이다.
SAMPLE = """---
form: structured
---

# 검토 결과를 정리한다

**하반기 검토 범위** — 한 장 조망

| 항목 | 비고 |
|---|---|
| 기한 | 9월 4일까지 |

- **되돌리기** 되돌리기가 가장 비싸다
"""


def load():
    spec = importlib.util.spec_from_file_location("doc_style_check", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(target: Path, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(CHECKER), str(target), "-v", *flags],
        capture_output=True, text=True, encoding="utf-8",
    )


class RuleInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CHECKER.is_file():
            raise unittest.SkipTest(f"검사기가 없습니다: {CHECKER}")
        cls.mod = load()
        cls.source = CHECKER.read_text(encoding="utf-8")

    def emitted_kinds(self) -> set[str]:
        """검사기가 실제로 내는 갈래 이름을 소스에서 긁는다."""
        kinds = set(re.findall(
            r"(?:err|warn)\.append\(\(\s*(?:n|0|start \+ k \+ 1),\s*'([^']+)'", self.source))
        kinds |= set(re.findall(r"(?:err|warn)\.append\(\(\s*'([^']+)'", self.source))
        kinds |= {k for k, *_ in self.mod.TRANSLATIONESE}
        return kinds

    def test_inventory_covers_every_kind(self) -> None:
        """목록에서 빠진 갈래는 끌 수도 없고 `--list-rules` 에도 안 보인다."""
        missing = sorted(self.emitted_kinds() - set(self.mod.ALL_KINDS))
        self.assertEqual([], missing, f"목록에 없는 갈래: {missing}")

    def test_inventory_has_no_phantom_kinds(self) -> None:
        """검사기가 안 내는 이름을 목록에 두면 끈 줄 알았던 것이 안 꺼진다."""
        extra = sorted(set(self.mod.ALL_KINDS) - self.emitted_kinds())
        self.assertEqual([], extra, f"검사기가 내지 않는 갈래: {extra}")

    def test_unknown_name_in_config_stops(self) -> None:
        """오타를 조용히 넘기면 끄려던 검사가 안 꺼진 채 통과로 읽힌다."""
        with self.assertRaises(ValueError):
            self.mod._expand(["서술형 종겷"], "시험")


class SelectionBehaviourTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CHECKER.is_file():
            raise unittest.SkipTest(f"검사기가 없습니다: {CHECKER}")

    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.doc = self.root / "sample.md"
        self.doc.write_text(SAMPLE, encoding="utf-8")

    def tearDown(self) -> None:
        self.dir.cleanup()

    def config(self, body: str) -> None:
        (self.root / "korean-qa.toml").write_text(body, encoding="utf-8")

    def kinds(self, out: str, mark: str) -> list[str]:
        return re.findall(rf"{mark} \[([^\]]+)\]", out)

    def test_baseline_finds_several_kinds(self) -> None:
        """표본이 실제로 여러 갈래를 낸다 — 안 그러면 뒤 시험이 아무것도 안 잰다."""
        out = run(self.doc).stdout
        found = set(self.kinds(out, "❌")) | set(self.kinds(out, "⚠️ "))
        self.assertGreaterEqual(len(found), 3, out)

    def test_off_removes_the_kind(self) -> None:
        before = set(self.kinds(run(self.doc).stdout, "❌"))
        self.assertIn("서술형 종결", before)
        self.config('[rules]\noff = ["서술형 종결"]\n')
        after = set(self.kinds(run(self.doc).stdout, "❌"))
        self.assertNotIn("서술형 종결", after)

    def test_group_name_turns_off_the_whole_group(self) -> None:
        self.config('[rules]\noff = ["구조"]\n')
        out = run(self.doc).stdout
        for kind in set(self.kinds(out, "❌")) | set(self.kinds(out, "⚠️ ")):
            self.assertNotEqual("구조", load().ALL_KINDS[kind], out)

    def test_warn_demotes_without_dropping(self) -> None:
        self.config('[rules]\nwarn = ["서술형 종결"]\n')
        out = run(self.doc).stdout
        self.assertNotIn("서술형 종결", self.kinds(out, "❌"))
        self.assertIn("서술형 종결", self.kinds(out, "⚠️ "))

    def test_demoted_error_no_longer_fails_the_run(self) -> None:
        """오류가 0이 되면 종료 코드도 0이어야 한다 — 게이트가 이 값을 본다."""
        self.config('[rules]\noff = ["문장", "구조", "낱말", "번역투", "안내"]\n')
        self.assertEqual(0, run(self.doc).returncode)

    def test_err_promotes_a_warning(self) -> None:
        self.config('[rules]\nerr = ["스캔 가치 없는 라벨"]\n')
        out = run(self.doc).stdout
        self.assertIn("스캔 가치 없는 라벨", self.kinds(out, "❌"))

    def test_no_rules_ignores_the_config(self) -> None:
        """발행 게이트는 설정이 무엇을 끄든 전부 봐야 한다."""
        self.config('[rules]\noff = ["서술형 종결"]\n')
        self.assertIn("서술형 종결", self.kinds(run(self.doc, "--no-rules").stdout, "❌"))

    def test_turning_something_off_is_printed(self) -> None:
        """조용히 끄면 「오류 0」이 통과인지 안 본 것인지 갈리지 않는다."""
        self.config('[rules]\noff = ["서술형 종결"]\n')
        out = run(self.doc).stdout
        self.assertIn("갈래 설정", out)
        self.assertIn("⊘ 서술형 종결", out)
        tail = out.strip().splitlines()[-1]
        self.assertIn("갈래 설정 적용", tail, f"합계 줄에 안 적혔습니다: {tail}")

    def test_no_config_changes_nothing(self) -> None:
        """설정이 없으면 예전과 똑같이 돈다."""
        self.assertEqual(run(self.doc).stdout, run(self.doc, "--no-rules").stdout)

    def test_broken_config_stops_rather_than_ignoring(self) -> None:
        self.config('[rules]\noff = ["없는 갈래 이름"]\n')
        done = run(self.doc)
        self.assertEqual(1, done.returncode)
        self.assertIn("모르는 이름", done.stdout)


if __name__ == "__main__":
    unittest.main()
