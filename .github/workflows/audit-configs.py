# NOTE! Fully slop-coded, this exists to help maintain config-manifest.toml without 
# about a billion hours of my time in an attempt to not retain config files for mods removed from the modlist.

#!/usr/bin/env python3
"""
Audit Packwiz mods against version-controlled Minecraft configuration files.

Designed for ABM-3:
  mods/*.pw.toml
  config/**
  defaultconfigs/**
  docs/config-manifest.toml

Python 3.11+ only (uses tomllib). No third-party packages required.

Exit codes:
  0 = clean
  1 = warnings only
  2 = errors found

Manifest example:

[mods.aether-ii]
configs = ["config/aether_ii-common.toml"]

[mods.kubejs]
configs = ["config/kubejs-client.toml"]
# If a mod has been reviewed and intentionally has no shipped config:
# configless = true

The table key must match the Packwiz metadata filename without ".pw.toml":
"mods/aether-ii.pw.toml" -> [mods.aether-ii]
"""

from __future__ import annotations

import argparse
import difflib
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


IGNORED_NAMES = {".gitkeep", ".DS_Store"}
CONFIG_ROOTS = ("config", "defaultconfigs")


@dataclass(frozen=True)
class Mod:
    key: str
    path: Path
    name: str
    filename: str
    side: str


def load_toml(path: Path) -> dict:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RuntimeError(f"Could not read TOML {path}: {exc}") from exc


def discover_mods(repo: Path) -> dict[str, Mod]:
    mods_dir = repo / "mods"
    found: dict[str, Mod] = {}

    if not mods_dir.is_dir():
        raise RuntimeError(f"Missing Packwiz mods directory: {mods_dir}")

    for path in sorted(mods_dir.glob("*.pw.toml")):
        data = load_toml(path)
        key = path.name.removesuffix(".pw.toml")
        found[key] = Mod(
            key=key,
            path=path.relative_to(repo),
            name=str(data.get("name", key)),
            filename=str(data.get("filename", "")),
            side=str(data.get("side", "unknown")),
        )

    return found


def discover_configs(repo: Path) -> set[str]:
    configs: set[str] = set()

    for root_name in CONFIG_ROOTS:
        root = repo / root_name
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if not path.is_file() or path.name in IGNORED_NAMES:
                continue
            configs.add(path.relative_to(repo).as_posix())

    return configs


def normalise(text: str) -> str:
    return "".join(ch.lower() for ch in text if ch.isalnum())


def ownership_hint(config_path: str, mods: dict[str, Mod]) -> str | None:
    """Best-effort hint only; never used to decide ownership."""
    stem = Path(config_path).name
    norm_config = normalise(stem)

    candidates: list[tuple[float, str]] = []
    for key, mod in mods.items():
        tokens = {
            normalise(key),
            normalise(mod.name),
        }

        # Jar filenames often include useful project/mod names.
        if mod.filename:
            tokens.add(normalise(mod.filename.split("-")[0]))

        score = max(
            (
                difflib.SequenceMatcher(None, norm_config, token).ratio()
                for token in tokens
                if token
            ),
            default=0.0,
        )

        # Strong substring matches are more useful than fuzzy similarity.
        if any(token and token in norm_config for token in tokens):
            score = max(score, 0.90)

        candidates.append((score, key))

    if not candidates:
        return None

    score, key = max(candidates)
    return key if score >= 0.58 else None


def load_manifest(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}

    data = load_toml(path)
    mods = data.get("mods", {})
    if not isinstance(mods, dict):
        raise RuntimeError(f"{path}: [mods] must be a TOML table")

    result: dict[str, dict] = {}
    for key, value in mods.items():
        if not isinstance(value, dict):
            raise RuntimeError(f"{path}: [mods.{key}] must be a TOML table")
        result[str(key)] = value

    return result


def print_group(title: str, items: list[str]) -> None:
    if not items:
        return
    print(f"\n{title}")
    for item in items:
        print(f"  - {item}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit Packwiz mod metadata against shipped Minecraft configs."
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: current directory)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("docs/config-manifest.toml"),
        help="Manifest path relative to repo root",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors (useful in CI)",
    )
    args = parser.parse_args()

    repo = args.repo.resolve()
    manifest_path = args.manifest
    if not manifest_path.is_absolute():
        manifest_path = repo / manifest_path

    try:
        mods = discover_mods(repo)
        actual_configs = discover_configs(repo)
        manifest = load_manifest(manifest_path)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    # Validate manifest entries and build claimed config ownership.
    claimed_by: dict[str, str] = {}

    for key, entry in sorted(manifest.items()):
        configs = entry.get("configs", [])
        configless = bool(entry.get("configless", False))

        if not isinstance(configs, list) or not all(isinstance(x, str) for x in configs):
            errors.append(f"{key}: 'configs' must be an array of paths")
            continue

        if configless and configs:
            errors.append(f"{key}: cannot set configless=true while also listing configs")

        if key not in mods:
            errors.append(
                f"{key}: manifest entry exists but mods/{key}.pw.toml is absent "
                "(removed mod / stale manifest?)"
            )

        for config in configs:
            config = Path(config).as_posix()

            if not (
                config == "config"
                or config.startswith("config/")
                or config == "defaultconfigs"
                or config.startswith("defaultconfigs/")
            ):
                errors.append(
                    f"{key}: manifest path is outside config/defaultconfigs: {config}"
                )

            previous = claimed_by.get(config)
            if previous and previous != key:
                errors.append(
                    f"{config}: claimed by both '{previous}' and '{key}'"
                )
            else:
                claimed_by[config] = key

            if config not in actual_configs:
                errors.append(f"{key}: expected config is missing: {config}")

    # Mods not reviewed in the manifest.
    for key, mod in sorted(mods.items()):
        if key not in manifest:
            warnings.append(
                f"{key} ({mod.name}): not reviewed in config manifest; "
                f"add [mods.{key}] with configs=[...] or configless=true"
            )

    # Files shipped but not claimed by any active manifest entry.
    for config in sorted(actual_configs):
        if config not in claimed_by:
            hint = ownership_hint(config, mods)
            suffix = f" (possible owner: {hint})" if hint else ""
            warnings.append(f"unowned config: {config}{suffix}")

    # Manifest paths that exist and are owned by currently installed mods.
    for config, owner in sorted(claimed_by.items()):
        if owner in mods and config in actual_configs:
            info.append(f"{config} -> {owner}")

    print(
        f"ABM-3 config audit: {len(mods)} Packwiz mods, "
        f"{len(actual_configs)} shipped config files, "
        f"{len(manifest)} reviewed mods."
    )

    print_group("ERRORS", errors)
    print_group("WARNINGS", warnings)

    if info:
        print(f"\nOK: {len(info)} manifest-listed config file(s) are present.")

    if errors:
        print(f"\nResult: FAIL ({len(errors)} error(s), {len(warnings)} warning(s))")
        return 2

    if warnings:
        if args.strict:
            print(f"\nResult: FAIL --strict ({len(warnings)} warning(s))")
            return 2
        print(f"\nResult: WARN ({len(warnings)} warning(s))")
        return 1

    print("\nResult: CLEAN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
