"""서브에이전트 정의 파일의 머리말이 실제로 먹히는 모양인지 본다.

**왜 이 시험이 필요한가.** 머리말 값이 틀리면 **조용히 무시된다.** `effort: mid`
라고 적으면 오류가 아니라 기본 깊이로 돌고, 그 상태로 재면 「깊이를 바꿔도 차이가
없다」는 틀린 결론이 나온다. 2026-09-16 실측에서 이미 그 언저리를 겪었다 —
haiku 4.5 에는 `effort` 항목 자체가 없어서 거기서 쟀으면 같은 오독을 했을 것이다
(`docs/ai-filter-experiment-20260916.md` §1).

**`omitClaudeMd` 를 특히 본다.** 이것이 빠지면 서브에이전트가 프로젝트
`CLAUDE.md` 를 싣고 돈다. 실측에서 sonnet 이 141개 중 139개를 「이 저장소에
정착된 표현」이라며 정상으로 넘겼다 — 판정층이 통째로 무력해진다.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import install  # noqa: E402
import repo_paths  # noqa: E402

#: 실행 파일의 모델 목록에서 확인한 값. `max` 까지 다섯이다.
EFFORT_VALUES = {"low", "medium", "high", "xhigh", "max"}

#: `effort` 를 받는 모델. haiku 는 `capabilities` 가 `context_management` 뿐이라
#: 적어 두어도 안 먹는다 — 적어 두면 「조절했다」는 착각이 남는다.
MODELS_WITH_EFFORT = {"sonnet", "opus", "fable"}


def frontmatter(path: Path) -> dict[str, str]:
    """머리말을 `열쇠: 값` 으로 읽는다 — 중첩이 없으므로 한 겹만 본다."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip()
    return out


class AgentDefinitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.files = sorted(repo_paths.AGENTS.glob("*.md"))

    def test_there_is_at_least_one_definition(self) -> None:
        self.assertTrue(self.files, f"{repo_paths.AGENTS} 아래에 정의가 없다")

    def test_name_matches_the_file_name(self) -> None:
        """이름이 어긋나면 `subagent_type` 으로 못 부른다."""
        for path in self.files:
            with self.subTest(path.name):
                self.assertEqual(frontmatter(path).get("name"), path.stem)

    def test_effort_value_is_one_of_the_five(self) -> None:
        for path in self.files:
            effort = frontmatter(path).get("effort")
            if effort is None:
                continue
            with self.subTest(path.name):
                self.assertIn(effort, EFFORT_VALUES)

    def test_effort_is_only_written_where_the_model_takes_it(self) -> None:
        """haiku 에 `effort` 를 적어 두면 안 먹는데 적힌 대로 믿게 된다."""
        for path in self.files:
            fm = frontmatter(path)
            if "effort" not in fm:
                continue
            with self.subTest(path.name):
                self.assertIn(fm.get("model"), MODELS_WITH_EFFORT,
                              "이 모델은 effort 를 안 받는다")

    def test_project_rules_are_not_loaded(self) -> None:
        """규칙 파일이 실려 들어가면 판정이 무너진다 — 실측으로 139/141 이 정상 판정."""
        for path in self.files:
            with self.subTest(path.name):
                self.assertEqual(frontmatter(path).get("omitClaudeMd"), "true")

    def test_install_carries_every_definition(self) -> None:
        """⛔ 옮기는 목록에서 빠지면 **설치한 PC 에서는 그 층이 아예 없다.**"""
        targets = {dst for _, dst in install.pairs()}
        for path in self.files:
            with self.subTest(path.name):
                self.assertIn(repo_paths.installed("agents", path.name), targets)


if __name__ == "__main__":
    unittest.main()
