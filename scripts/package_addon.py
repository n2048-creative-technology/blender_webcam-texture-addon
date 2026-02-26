#!/usr/bin/env python3
import argparse
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


def build_zip(root_dir: Path, addon_name: str, include_wheels: bool, wheels_dir: Path) -> Path:
    dist_dir = root_dir / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)

    zip_path = dist_dir / f"{addon_name}.zip"
    src_init = root_dir / "__init__.py"
    if not src_init.exists():
        raise FileNotFoundError(f"Missing addon entrypoint: {src_init}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        addon_dir = tmp_root / addon_name
        addon_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_init, addon_dir / "__init__.py")

        if include_wheels:
            if not wheels_dir.exists():
                raise FileNotFoundError(f"Wheels directory not found: {wheels_dir}")
            shutil.copytree(wheels_dir, addon_dir / "wheels")

        if zip_path.exists():
            zip_path.unlink()

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in addon_dir.rglob("*"):
                if path.is_dir():
                    continue
                rel = path.relative_to(tmp_root)
                zf.write(path, rel.as_posix())

    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Package the Blender addon into a distributable zip.")
    parser.add_argument("--addon-name", default="webcam_uv_texture_stream", help="Top-level addon folder name inside the zip")
    parser.add_argument("--include-wheels", action="store_true", help="Include wheels/ directory in the zip")
    parser.add_argument("--wheels-dir", default="wheels", help="Path to wheels directory")
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parents[1]
    wheels_dir = (root_dir / args.wheels_dir).resolve()

    zip_path = build_zip(root_dir, args.addon_name, args.include_wheels, wheels_dir)
    print(f"Created {zip_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
