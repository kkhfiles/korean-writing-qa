"""검사기 자체 시험이 실제로 도는지 본다.

**왜 있나.** `assets/doc-style-check-test.py` 는 2026-09-15 까지 **저장소 밖에**
있었다. 전역 규칙은 그것을 쓰라고 적어 두었는데 이력에 한 번도 없었고 설치
목록에도 없어 아무도 돌리지 않았다. 그 사이 시료 본문의 표현을 나중에 생긴
규칙이 잡게 되어 **시험이 깨진 채 여드레가 지났다.**

「규칙을 썼다 ≠ 규칙이 적용된다」가 검사기의 시험 자신에게 난 사례다.
"""
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SELFTEST = os.path.join(ROOT, "assets", "doc-style-check-test.py")


class CheckerSelfTestRuns(unittest.TestCase):

    def test_the_file_is_in_the_repository(self) -> None:
        """설치본에만 있으면 기계가 바뀌는 날 사라진다."""
        self.assertTrue(os.path.exists(SELFTEST),
                        "assets/doc-style-check-test.py 가 없습니다")

    def test_it_passes(self) -> None:
        done = subprocess.run([sys.executable, "-X", "utf8", SELFTEST],
                              capture_output=True, text=True,
                              encoding="utf-8", cwd=ROOT)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)

    def test_install_carries_it(self) -> None:
        """설치 목록에 들어 있어야 전역 규칙이 가리키는 경로가 살아 있다."""
        sys.path.insert(0, ROOT)
        import install
        names = {dst.name for _src, dst in install.pairs()}
        self.assertIn("doc-style-check-test.py", names,
                      "install.py 가 자체 시험을 안 옮깁니다")


if __name__ == "__main__":
    unittest.main()
