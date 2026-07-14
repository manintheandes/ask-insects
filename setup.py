from __future__ import annotations

import json
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py


ROOT = Path(__file__).resolve().parent
RESOURCE_PACKAGE = "askinsects.resources"
CONFIG_RESOURCES = (
    ROOT / "config" / "insect-evidence-package.json",
    ROOT / "config" / "insect-intelligence-programs.json",
)
def canonical_resource_files() -> tuple[Path, ...]:
    context_config = json.loads(CONFIG_RESOURCES[0].read_text(encoding="utf-8"))
    package_version = context_config.get("package_version")
    if not isinstance(package_version, str) or not package_version.strip():
        raise RuntimeError("context config has no package_version")
    published = (
        ROOT
        / "public"
        / "evidence-packages"
        / f"ask-insects-evidence-package-{package_version}.json"
    )

    resources = (*CONFIG_RESOURCES, published)
    missing = [path for path in resources if not path.is_file()]
    if missing:
        names = ", ".join(path.relative_to(ROOT).as_posix() for path in missing)
        raise RuntimeError(f"canonical Ask Insects resources are missing: {names}")
    return resources


class BuildPyWithCanonicalResources(_build_py):
    """Copy canonical root JSON into the wheel without duplicating it in git."""

    def build_package_data(self) -> None:
        super().build_package_data()
        target_dir = Path(self.build_lib).joinpath(*RESOURCE_PACKAGE.split("."))
        self.mkpath(target_dir.as_posix())
        for source in canonical_resource_files():
            self.copy_file(source.as_posix(), (target_dir / source.name).as_posix())

    def get_outputs(self, include_bytecode: bool = True) -> list[str]:
        outputs = super().get_outputs(include_bytecode)
        target_dir = Path(self.build_lib).joinpath(*RESOURCE_PACKAGE.split("."))
        outputs.extend(
            (target_dir / source.name).as_posix()
            for source in canonical_resource_files()
        )
        return outputs


setup(cmdclass={"build_py": BuildPyWithCanonicalResources})
