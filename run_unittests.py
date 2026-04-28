import argparse
import unittest


class _Color:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    RESET = "\033[0m"


def _colorize(text: str, color: str) -> str:
    return f"{color}{text}{_Color.RESET}"


class ColorTextTestResult(unittest.TextTestResult):
    def addSuccess(self, test: unittest.case.TestCase) -> None:
        super().addSuccess(test)
        self.stream.writeln(f"{test.id()} ... {_colorize('✓ OK', _Color.GREEN)}")

    def addFailure(self, test: unittest.case.TestCase, err) -> None:  # type: ignore[override]
        super().addFailure(test, err)
        self.stream.writeln(f"{test.id()} ... {_colorize('X FAILED', _Color.RED)}")

    def addError(self, test: unittest.case.TestCase, err) -> None:  # type: ignore[override]
        super().addError(test, err)
        self.stream.writeln(f"{test.id()} ... {_colorize('! ERROR', _Color.RED)}")

    def addSkip(self, test: unittest.case.TestCase, reason: str) -> None:
        super().addSkip(test, reason)
        self.stream.writeln(
            f"{test.id()} ... {_colorize(f'→ SKIPPED ({reason})', _Color.YELLOW)}"
        )

    def addExpectedFailure(self, test: unittest.case.TestCase, err) -> None:  # type: ignore[override]
        super().addExpectedFailure(test, err)
        self.stream.writeln(
            f"{test.id()} ... {_colorize('~ EXPECTED FAILURE', _Color.YELLOW)}"
        )

    def addUnexpectedSuccess(self, test: unittest.case.TestCase) -> None:
        super().addUnexpectedSuccess(test)
        self.stream.writeln(
            f"{test.id()} ... {_colorize('? UNEXPECTED SUCCESS', _Color.CYAN)}"
        )


class ColorTextTestRunner(unittest.TextTestRunner):
    resultclass = ColorTextTestResult


def _build_suite(targets: list[str]) -> unittest.TestSuite:
    loader = unittest.defaultTestLoader
    if targets:
        return loader.loadTestsFromNames(targets)
    return loader.discover("tests", pattern="test_*.py")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run unittest with colored per-test status output."
    )
    parser.add_argument(
        "tests",
        nargs="*",
        help="Optional test modules/classes/methods. Defaults to discovering tests/test_*.py.",
    )
    args = parser.parse_args()

    suite = _build_suite(args.tests)
    runner = ColorTextTestRunner(verbosity=0)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
