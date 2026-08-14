#!/usr/bin/env python3
"""Build the effective MathCAT rules tree from the pristine vendored one.

``vendor/Rules`` stays byte-identical to the sha256-pinned upstream archive so
``bootstrap_vendor.sh`` can re-download it at any time. Our corrections to the
machine-translated Vietnamese rules live in ``rules_overrides/<lang>.json`` and
are applied here into a separate output tree.

An edit either rewrites a single line (``find``/``replace``) or a contiguous run
of lines (``find_block``/``replace_block``, which may also insert new rules).
Every edit must hit an exact number of times; a miss fails the build instead of
silently shipping the upstream pronunciation.
"""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_RULES_DIR = BASE_DIR / "vendor" / "Rules"
DEFAULT_OVERRIDES_DIR = BASE_DIR / "rules_overrides"
DEFAULT_OUT_DIR = BASE_DIR / "rules"


class OverrideError(RuntimeError):
    pass


def _strip_eol(line: str) -> tuple[str, str]:
    eol = "\r" if line.endswith("\r") else ""
    return line[: len(line) - len(eol)], eol


def _apply_edit(lines: list[str], edit: dict) -> tuple[list[str], int, str]:
    if "find_block" in edit:
        find, replace = edit["find_block"], edit["replace_block"]
    else:
        find, replace = [edit["find"]], [edit["replace"]]

    out: list[str] = []
    index = 0
    hits = 0
    while index < len(lines):
        window = [_strip_eol(line)[0] for line in lines[index : index + len(find)]]
        if window != find:
            out.append(lines[index])
            index += 1
            continue
        # Reuse the first matched line's ending so CRLF files stay CRLF.
        eol = _strip_eol(lines[index])[1]
        out.extend(line + eol for line in replace)
        index += len(find)
        hits += 1
    return out, hits, "\n".join(find)


def _patch_text(text: str, edits: list[dict], file_name: str) -> tuple[str, int]:
    # Rule files mix LF and CRLF endings, so match on the line body only.
    lines = text.split("\n")
    applied = 0
    for edit in edits:
        lines, hits, shown = _apply_edit(lines, edit)
        if hits != edit["count"]:
            raise OverrideError(
                f"{file_name}: expected {edit['count']} match(es) for "
                f"{shown!r}, found {hits}. Upstream rules changed — "
                f"re-check rules_overrides before shipping."
            )
        applied += hits
    return "\n".join(lines), applied


def _patch_zip(zip_path: Path, edits_by_file: dict[str, list[dict]]) -> int:
    with zipfile.ZipFile(zip_path) as source:
        infos = source.infolist()
        payloads = {info.filename: source.read(info.filename) for info in infos}

    unknown = set(edits_by_file) - set(payloads)
    if unknown:
        raise OverrideError(
            f"{zip_path.name}: no such entries in the rules archive: {sorted(unknown)}"
        )

    applied = 0
    for name, edits in edits_by_file.items():
        text = payloads[name].decode("utf-8")
        text, hits = _patch_text(text, edits, name)
        payloads[name] = text.encode("utf-8")
        applied += hits

    tmp_path = zip_path.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp_path, "w") as target:
        for info in infos:
            # Load-bearing: MathCAT's zip reader only handles the bzip2 method
            # these archives ship with, so reuse each entry's ZipInfo verbatim
            # rather than picking a compression type here.
            target.writestr(info, payloads[info.filename])
    tmp_path.replace(zip_path)
    return applied


def apply_overrides(
    rules_dir: Path = DEFAULT_RULES_DIR,
    overrides_dir: Path = DEFAULT_OVERRIDES_DIR,
    out_dir: Path = DEFAULT_OUT_DIR,
) -> dict[str, int]:
    if not rules_dir.is_dir():
        raise OverrideError(f"Rules dir not found: {rules_dir}. Run bootstrap_vendor.sh first.")
    if out_dir.resolve() == rules_dir.resolve():
        raise OverrideError("Refusing to patch the pristine vendored rules in place")

    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(rules_dir, out_dir)

    summary: dict[str, int] = {}
    for override_file in sorted(overrides_dir.glob("*.json")):
        spec = json.loads(override_file.read_text(encoding="utf-8"))
        language = spec["language"]
        zip_path = out_dir / "Languages" / language / f"{language}.zip"
        if not zip_path.is_file():
            raise OverrideError(f"Missing rules archive for language {language!r}: {zip_path}")

        edits_by_file: dict[str, list[dict]] = {}
        for edit in spec["edits"]:
            edits_by_file.setdefault(edit["file"], []).append(edit)
        summary[language] = _patch_zip(zip_path, edits_by_file)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules-dir", type=Path, default=DEFAULT_RULES_DIR)
    parser.add_argument("--overrides-dir", type=Path, default=DEFAULT_OVERRIDES_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    summary = apply_overrides(args.rules_dir, args.overrides_dir, args.out_dir)
    for language, applied in summary.items():
        print(f"{language}: applied {applied} rule override(s) -> {args.out_dir}")


if __name__ == "__main__":
    main()
