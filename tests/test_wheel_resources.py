from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_RESOURCES = (
    REPO_ROOT / "config" / "insect-evidence-package.json",
    REPO_ROOT / "config" / "insect-intelligence-programs.json",
)
PUBLISHED_RESOURCES = tuple(
    sorted(
        (REPO_ROOT / "public" / "evidence-packages").glob(
            "ask-insects-evidence-package-*.json"
        )
    )
)


class WheelResourceTests(unittest.TestCase):
    def test_clean_wheel_exposes_canonical_json_through_importlib_resources(self):
        self.assertTrue(PUBLISHED_RESOURCES, "no published evidence package found")
        expected = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (*CONFIG_RESOURCES, *PUBLISHED_RESOURCES)
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source"
            wheelhouse = root / "wheelhouse"
            installed = root / "installed"
            run_dir = root / "run"
            source.mkdir()
            run_dir.mkdir()

            for name in ("pyproject.toml", "setup.py", "README.md"):
                path = REPO_ROOT / name
                if path.exists():
                    shutil.copy2(path, source / name)
            shutil.copytree(
                REPO_ROOT / "askinsects",
                source / "askinsects",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            (source / "config").mkdir()
            for path in CONFIG_RESOURCES:
                shutil.copy2(path, source / "config" / path.name)
            published_dir = source / "public" / "evidence-packages"
            published_dir.mkdir(parents=True)
            for path in PUBLISHED_RESOURCES:
                shutil.copy2(path, published_dir / path.name)

            source_resources = source / "askinsects" / "resources"
            self.assertEqual(list(source_resources.glob("*.json")), [])

            uv = shutil.which("uv")
            self.assertIsNotNone(uv, "uv is required to build the isolated test wheel")
            self._run(
                uv,
                "build",
                "--wheel",
                "--out-dir",
                wheelhouse.as_posix(),
                source.as_posix(),
                cwd=root,
            )
            wheels = list(wheelhouse.glob("*.whl"))
            self.assertEqual(len(wheels), 1)
            self._run(
                uv,
                "pip",
                "install",
                "--no-deps",
                "--target",
                installed.as_posix(),
                wheels[0].as_posix(),
                cwd=root,
            )

            verification = self._run(
                sys.executable,
                "-I",
                "-c",
                textwrap.dedent(
                    """
                    import hashlib
                    from importlib.resources import files
                    import json
                    import sys

                    sys.path.insert(0, sys.argv[1])
                    expected = json.loads(sys.argv[2])
                    resources = files("askinsects.resources")
                    actual = {}
                    for name, digest in expected.items():
                        data = resources.joinpath(name).read_bytes()
                        json.loads(data)
                        actual[name] = hashlib.sha256(data).hexdigest()
                    if actual != expected:
                        raise SystemExit(f"resource digests differ: {actual!r}")
                    print(json.dumps(actual, sort_keys=True))
                    """
                ),
                installed.as_posix(),
                json.dumps(expected, sort_keys=True),
                cwd=run_dir,
            )

            self.assertEqual(json.loads(verification.stdout), expected)
            self.assertEqual(list(source_resources.glob("*.json")), [])

    def _run(self, *args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
        self.assertEqual(
            result.returncode,
            0,
            f"command failed: {' '.join(args)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        return result


if __name__ == "__main__":
    unittest.main()
