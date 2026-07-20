from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

from askinsects.agent_setup import REPO_SKILL_DIR, install_askinsects_skill, skill_manifest


class AgentSetupTests(unittest.TestCase):
    def test_project_defaults_normal_questions_to_reliable_router_model(self):
        config = tomllib.loads(Path(".codex/config.toml").read_text(encoding="utf-8"))

        self.assertEqual(config["model"], "gpt-5.4")
        self.assertEqual(config["model_reasoning_effort"], "low")

    def test_repo_instructions_make_the_hosted_call_the_first_normal_action(self):
        source = Path("AGENTS.md").read_text(encoding="utf-8")
        text = " ".join(source.split())

        self.assertLess(
            source.index("## Normal Question Fast Path"),
            source.index("## Read Order"),
        )

        for term in (
            "Do not spend a reasoning turn deciding how to route it",
            "As the first action",
            "preferred first and only operational command",
            "the user's exact complete question",
            "Do not load the installed skill",
            "adding a new insect",
            "answer-routing design",
            "Do not inspect memory",
            "Chronicle",
            "Do not emit a progress update",
            "exactly one visible assistant message",
            "Return it immediately and verbatim without another reasoning turn or command",
            "yields a session ID",
            "continue the same process",
            "write_stdin",
            "The shell command must begin with `ask-insects` and end with `--answer-only`",
            "POSIX single-quoted shell argument",
            "replace every embedded apostrophe",
            "Never retry after a shell-quoting error",
            "Do not add comments, timing directives, or wrapper text to the shell command",
            "uses a reliable Codex routing model at low reasoning",
            "not a second command",
            "Never call image generation",
            "unless the user explicitly asks for a visual",
            "Preserve canonical labels",
            "stdout",
            "verbatim",
        ):
            self.assertIn(term, text)
        self.assertNotIn("// @exec:", source)

    def test_repo_skill_encodes_current_product_and_answer_contract(self):
        source = (REPO_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        text = " ".join(source.split())

        self.assertLessEqual(len(source.splitlines()), 70)

        for term in (
            "SWD crop repellent",
            "human mosquito repellent",
            "diamondback moth",
            "adding a new insect",
            "answer-routing design",
            "hosted production source plane",
            "under 60 seconds",
            "source id",
            "row or locator",
            "Do not run setup-agent during a user question",
            "Do not inspect memory",
            "Do not emit a progress update",
            "run a second Ask Insects call",
            "Never call image generation",
            "unless the user explicitly asks for a visual",
            "yield a session ID",
            "write_stdin",
            "cell ID",
            "functions.wait",
            "Continue that same process",
            "Never discard a yielded command",
            "Do not add comments, timing directives, or wrapper text to the shell command",
            "write every cited locator in full",
            "--answer-only",
            "stdout",
            "verbatim",
        ):
            self.assertIn(term, text)
        self.assertNotIn("current top-level product goal is Aedes-first", text)
        self.assertNotIn("/Users/josh/projects/ask-insects", text)

        frontmatter = " ".join(source.split("---", 2)[1].split())
        for term in (
            "Do not open this file for a normal answer",
            "adding a new insect",
            "answer-routing design",
            "first hosted command",
            "POSIX single-quoted shell argument",
            "replace every embedded apostrophe",
            "Never retry after a shell-quoting error",
            "If it yields a session ID",
            "write_stdin until exit",
            "cell ID",
            "functions.wait",
            "Never call image generation",
            "return stdout verbatim",
        ):
            self.assertIn(term, frontmatter)

    def test_installer_atomically_replaces_and_verifies_skill_tree(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "askinsects"
            destination.mkdir(parents=True)
            (destination / "stale.txt").write_text("stale", encoding="utf-8")

            result = install_askinsects_skill(destination=destination)

            self.assertTrue(result["ok"])
            self.assertTrue(result["verified"])
            self.assertFalse((destination / "stale.txt").exists())
            self.assertEqual(skill_manifest(destination), skill_manifest(REPO_SKILL_DIR))
            self.assertEqual(result["file_count"], len(skill_manifest(REPO_SKILL_DIR)))

    def test_setup_agent_cli_installs_to_explicit_destination(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "askinsects"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "askinsects",
                    "setup-agent",
                    "--destination",
                    destination.as_posix(),
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["verified"])
            self.assertEqual(Path(payload["destination"]), destination.resolve())
            self.assertTrue((destination / "SKILL.md").exists())

    def test_local_runtime_installer_refreshes_cli_and_skill_together(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runtime = root / "runtime"
            bin_dir = root / "bin"
            skill_dir = root / "skills" / "askinsects"
            env = {
                **os.environ,
                "ASK_INSECTS_INSTALL_DIR": runtime.as_posix(),
                "ASK_INSECTS_BIN_DIR": bin_dir.as_posix(),
                "ASK_INSECTS_SKILL_DIR": skill_dir.as_posix(),
            }

            result = subprocess.run(
                ["bash", "scripts/install_local_runtime.sh"],
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            install_payload = json.loads(result.stdout)
            self.assertEqual(
                Path(install_payload["source"]),
                (runtime / "skills" / "askinsects").resolve(),
            )
            self.assertTrue((runtime / "askinsects" / "__init__.py").exists())
            self.assertTrue((runtime / "config" / "insect-intelligence-programs.json").exists())
            self.assertTrue((bin_dir / "ask-insects").exists())
            self.assertEqual(skill_manifest(skill_dir), skill_manifest(REPO_SKILL_DIR))

            help_result = subprocess.run(
                [(bin_dir / "ask-insects").as_posix(), "--help"],
                capture_output=True,
                text=True,
                env={**env, "ASK_INSECTS_REPO": runtime.as_posix()},
            )
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            self.assertIn("setup-agent", help_result.stdout)


if __name__ == "__main__":
    unittest.main()
