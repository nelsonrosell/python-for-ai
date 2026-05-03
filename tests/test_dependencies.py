from importlib import metadata
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_ROOT = PROJECT_ROOT / "requirements"


def _load_required_distributions(requirements_file: Path) -> list[str]:
    packages: list[str] = []

    for raw_line in requirements_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r "):
            nested_file = requirements_file.parent / line[3:].strip()
            packages.extend(_load_required_distributions(nested_file))
            continue

        package_name = line.split("==", maxsplit=1)[0].strip()
        if package_name:
            packages.append(package_name)

    return packages


class TestDependencies(unittest.TestCase):
    def test_required_python_distributions_are_installed(self) -> None:
        missing_packages: list[str] = []
        package_names = _load_required_distributions(
            REQUIREMENTS_ROOT / "dev.txt"
        )

        for package_name in package_names:
            with self.subTest(package=package_name):
                try:
                    metadata.distribution(package_name)
                except metadata.PackageNotFoundError:
                    missing_packages.append(package_name)

        if missing_packages:
            self.fail(
                "Missing required Python libraries: " +
                ", ".join(missing_packages)
            )


if __name__ == "__main__":
    unittest.main()
