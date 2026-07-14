from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import unittest
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_RESOURCES = (
    REPO_ROOT / "config" / "insect-evidence-package.json",
    REPO_ROOT / "config" / "insect-intelligence-programs.json",
)
PACKAGE_VERSION = json.loads(CONFIG_RESOURCES[0].read_text(encoding="utf-8"))[
    "package_version"
]
PUBLISHED_RESOURCE = (
    REPO_ROOT
    / "public"
    / "evidence-packages"
    / f"ask-insects-evidence-package-{PACKAGE_VERSION}.json"
)


class WheelResourceTests(unittest.TestCase):
    def test_sdist_builds_clean_wheel_with_only_current_canonical_json(self):
        self.assertTrue(PUBLISHED_RESOURCE.is_file(), "current evidence package is missing")
        expected = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (*CONFIG_RESOURCES, PUBLISHED_RESOURCE)
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source"
            sdist_dir = root / "sdist"
            extracted_dir = root / "extracted"
            wheelhouse = root / "wheelhouse"
            installed = root / "installed"
            run_dir = root / "run"
            source.mkdir()
            run_dir.mkdir()

            for name in ("pyproject.toml", "setup.py", "README.md", "MANIFEST.in"):
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
            shutil.copy2(PUBLISHED_RESOURCE, published_dir / PUBLISHED_RESOURCE.name)

            source_resources = source / "askinsects" / "resources"
            self.assertEqual(list(source_resources.glob("*.json")), [])

            uv = shutil.which("uv")
            self.assertIsNotNone(uv, "uv is required to build the isolated test wheel")
            self._run(
                uv,
                "build",
                "--sdist",
                "--out-dir",
                sdist_dir.as_posix(),
                source.as_posix(),
                cwd=root,
            )
            sdists = list(sdist_dir.glob("*.tar.gz"))
            self.assertEqual(len(sdists), 1)
            extracted_dir.mkdir()
            with tarfile.open(sdists[0], "r:gz") as archive:
                archive.extractall(extracted_dir, filter="data")
            extracted_sources = [path for path in extracted_dir.iterdir() if path.is_dir()]
            self.assertEqual(len(extracted_sources), 1)
            extracted_source = extracted_sources[0]
            self.assertTrue((extracted_source / "config" / CONFIG_RESOURCES[0].name).is_file())
            self.assertTrue(
                (
                    extracted_source
                    / "public"
                    / "evidence-packages"
                    / PUBLISHED_RESOURCE.name
                ).is_file()
            )
            self.assertEqual(
                [
                    path.name
                    for path in (extracted_source / "public" / "evidence-packages").glob("*.json")
                ],
                [PUBLISHED_RESOURCE.name],
            )
            self._run(
                uv,
                "build",
                "--wheel",
                "--out-dir",
                wheelhouse.as_posix(),
                extracted_source.as_posix(),
                cwd=root,
            )
            wheels = list(wheelhouse.glob("*.whl"))
            self.assertEqual(len(wheels), 1)
            with zipfile.ZipFile(wheels[0]) as wheel:
                resource_names = sorted(
                    Path(name).name
                    for name in wheel.namelist()
                    if "/resources/" in name and name.endswith(".json")
                )
            self.assertEqual(resource_names, sorted(expected))
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

            decoy_dir = run_dir / "config"
            decoy_dir.mkdir()
            (decoy_dir / "insect-intelligence-programs.json").write_text(
                json.dumps({"schema_version": "decoy"}),
                encoding="utf-8",
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
                    from askinsects.context_package import (
                        DEFAULT_CONTEXT_CONFIG,
                        DEFAULT_PROGRAM_CONFIG,
                        DEFAULT_PUBLISHED_PACKAGE,
                        load_context_config,
                        load_published_context_package,
                    )
                    from askinsects.sources.insect_intelligence_programs import (
                        DEFAULT_PROGRAM_LEDGER,
                        load_program_ledger,
                    )

                    expected = json.loads(sys.argv[2])
                    resources = files("askinsects.resources")
                    actual = {}
                    for name, digest in expected.items():
                        data = resources.joinpath(name).read_bytes()
                        json.loads(data)
                        actual[name] = hashlib.sha256(data).hexdigest()
                    if actual != expected:
                        raise SystemExit(f"resource digests differ: {actual!r}")
                    defaults = {
                        "context": DEFAULT_CONTEXT_CONFIG.name,
                        "program": DEFAULT_PROGRAM_CONFIG.name,
                        "program_ledger": DEFAULT_PROGRAM_LEDGER.name,
                        "published": DEFAULT_PUBLISHED_PACKAGE.name,
                    }
                    if defaults != {
                        "context": "insect-evidence-package.json",
                        "program": "insect-intelligence-programs.json",
                        "program_ledger": "insect-intelligence-programs.json",
                        "published": "ask-insects-evidence-package-2026-07-14.7.json",
                    }:
                        raise SystemExit(f"installed defaults are wrong: {defaults!r}")
                    if load_context_config()["package_version"] != "2026-07-14.7":
                        raise SystemExit("installed context config did not load")
                    if load_program_ledger(DEFAULT_PROGRAM_LEDGER)["schema_version"] != "insect-intelligence-programs.v1":
                        raise SystemExit("installed program ledger did not load")
                    published = load_published_context_package()
                    if published["package_version"] != "2026-07-14.7":
                        raise SystemExit("installed published release did not load")
                    print(json.dumps({"digests": actual, "defaults": defaults}, sort_keys=True))
                    """
                ),
                installed.as_posix(),
                json.dumps(expected, sort_keys=True),
                cwd=run_dir,
            )

            self.assertEqual(json.loads(verification.stdout)["digests"], expected)
            self.assertEqual(list(source_resources.glob("*.json")), [])

    def test_source_program_ledger_ignores_unrelated_working_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            decoy_dir = run_dir / "config"
            decoy_dir.mkdir()
            (decoy_dir / "insect-intelligence-programs.json").write_text(
                json.dumps({"schema_version": "decoy"}),
                encoding="utf-8",
            )
            result = self._run(
                sys.executable,
                "-I",
                "-c",
                textwrap.dedent(
                    """
                    import json
                    import sys
                    sys.path.insert(0, sys.argv[1])
                    from askinsects.sources.insect_intelligence_programs import (
                        DEFAULT_PROGRAM_LEDGER,
                        load_program_ledger,
                    )
                    payload = load_program_ledger(DEFAULT_PROGRAM_LEDGER)
                    print(json.dumps({
                        "default": str(DEFAULT_PROGRAM_LEDGER),
                        "schema_version": payload["schema_version"],
                    }))
                    """
                ),
                REPO_ROOT.as_posix(),
                cwd=run_dir,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["schema_version"], "insect-intelligence-programs.v1")
            self.assertEqual(
                Path(payload["default"]),
                REPO_ROOT / "config" / "insect-intelligence-programs.json",
            )

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
