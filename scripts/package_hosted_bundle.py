from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


INCLUDE_PATHS = [
    ".dockerignore",
    ".env.example",
    ".github/workflows/ci.yml",
    ".nvmrc",
    ".python-version",
    "README.md",
    "SECURITY.md",
    "requirements-ci.txt",
    "requirements-dev.txt",
    "assets",
    "backend",
    "data/evals",
    "deploy",
    "index.html",
    "project.md",
    "runtime",
    "scripts",
]


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a portable hosted-dev bundle for Docker-capable environments.")
    parser.add_argument(
        "--output-dir",
        default=str(project_root() / "build" / "hosted-bundle"),
        help="Target directory for the packaged bundle.",
    )
    return parser.parse_args()


def reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_path(root: Path, destination_root: Path, relative: str) -> None:
    source = root / relative
    target = destination_root / relative
    if not source.exists():
        raise RuntimeError(f"Required bundle path is missing: {relative}")
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def write_manifest(root: Path, destination_root: Path) -> None:
    manifest = {
        "bundle": "parallm-hosted-dev",
        "root": str(destination_root),
        "included": INCLUDE_PATHS,
        "entrypoints": {
            "compose": "deploy/compose.hosted-dev.yml",
            "composeRuntimeServiceOverride": "deploy/compose.hosted-dev.runtime-service.yml",
            "dockerBackend": "deploy/backend/Dockerfile",
            "dockerRuntime": "deploy/runtime/Dockerfile",
            "qa": "python scripts/qa_hosted_dev_stack.py",
        },
        "notes": [
            "Provide a real OpenAI key file and set LOOP_SECRET_SOURCE_FILE before docker compose up.",
            "Use deploy/compose.hosted-dev.runtime-service.yml when you want backend and runtime split into separate containers.",
        ],
    }
    manifest_path = destination_root / "build-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> int:
    root = project_root()
    destination_root = Path(parse_args().output_dir).resolve()
    reset_directory(destination_root)
    for relative in INCLUDE_PATHS:
        copy_path(root, destination_root, relative)
    write_manifest(root, destination_root)
    print(json.dumps({"ok": True, "outputDir": str(destination_root), "includedCount": len(INCLUDE_PATHS)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
