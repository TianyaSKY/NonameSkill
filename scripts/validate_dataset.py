#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


WS_RE = re.compile(r"\s+")


def default_dataset_path() -> Path:
    # scripts/validate_dataset.py -> skill_root/assets/dataset.jsonl
    return Path(__file__).resolve().parents[1] / "assets" / "dataset.jsonl"


def normalize_text(value: str) -> str:
    return WS_RE.sub(" ", value).strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate dataset.jsonl format and content quality."
    )
    parser.add_argument(
        "--dataset",
        default=str(default_dataset_path()),
        help="Path to dataset.jsonl",
    )
    parser.add_argument(
        "--min-instruction-len",
        type=int,
        default=6,
        help="Warn when instruction length is below this value",
    )
    parser.add_argument(
        "--min-output-len",
        type=int,
        default=30,
        help="Warn when output length is below this value",
    )
    parser.add_argument(
        "--max-output-len",
        type=int,
        default=30000,
        help="Warn when output length exceeds this value",
    )
    parser.add_argument(
        "--max-issues",
        type=int,
        default=20,
        help="Max detailed issue lines to print per category",
    )
    parser.add_argument(
        "--strict-warn",
        action="store_true",
        help="Treat warnings as failure (exit code 1)",
    )
    return parser.parse_args()


def read_rows(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    json_errors: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for i, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                json_errors.append(f"line {i}: JSONDecodeError: {e.msg}")
                continue
            if not isinstance(obj, dict):
                json_errors.append(f"line {i}: row must be an object")
                continue
            obj["_line"] = i
            rows.append(obj)
    return rows, json_errors


def shorten(s: str, limit: int = 120) -> str:
    s = normalize_text(s)
    if len(s) <= limit:
        return s
    return s[: limit - 3] + "..."


def main() -> int:
    args = parse_args()
    dataset_path = Path(args.dataset).resolve()

    if not dataset_path.exists():
        print(f"[ERROR] dataset not found: {dataset_path}")
        return 1

    rows, parse_errors = read_rows(dataset_path)

    missing_required: list[str] = []
    invalid_type: list[str] = []
    empty_required: list[str] = []
    short_instruction: list[str] = []
    short_output: list[str] = []
    long_output: list[str] = []

    dedupe: dict[str, list[int]] = {}

    required_fields = ("instruction", "input", "output")
    for row in rows:
        line = int(row["_line"])

        for field in required_fields:
            if field not in row:
                missing_required.append(f"line {line}: missing field `{field}`")

        for field in required_fields:
            if field in row and not isinstance(row[field], str):
                invalid_type.append(
                    f"line {line}: field `{field}` must be string, got {type(row[field]).__name__}"
                )

        instruction = row.get("instruction")
        output = row.get("output")
        model_input = row.get("input")

        if isinstance(instruction, str) and normalize_text(instruction) == "":
            empty_required.append("line %d: `instruction` is empty" % line)
        if isinstance(output, str) and normalize_text(output) == "":
            empty_required.append("line %d: `output` is empty" % line)

        if isinstance(instruction, str):
            instruction_norm = normalize_text(instruction)
            if len(instruction_norm) < args.min_instruction_len:
                short_instruction.append(
                    f"line {line}: instruction too short ({len(instruction_norm)}): {shorten(instruction_norm)}"
                )
            if instruction_norm:
                dedupe.setdefault(instruction_norm, []).append(line)

        if isinstance(output, str):
            output_norm = normalize_text(output)
            olen = len(output_norm)
            if olen < args.min_output_len:
                short_output.append(
                    f"line {line}: output too short ({olen}): {shorten(output_norm)}"
                )
            if olen > args.max_output_len:
                long_output.append(f"line {line}: output too long ({olen})")

        # Keep input type validation only; empty input is allowed.
        if model_input is not None and not isinstance(model_input, str):
            invalid_type.append(
                f"line {line}: field `input` must be string, got {type(model_input).__name__}"
            )

    duplicate_instruction = [
        f"lines {','.join(map(str, lines[:8]))}{'...' if len(lines) > 8 else ''}: "
        f"instruction duplicated ({len(lines)}x) -> {shorten(text)}"
        for text, lines in dedupe.items()
        if len(lines) > 1
    ]

    print(f"Dataset: {dataset_path}")
    print(f"Rows parsed: {len(rows)}")
    print("")

    def print_group(title: str, items: list[str], is_error: bool) -> None:
        level = "ERROR" if is_error else "WARN"
        print(f"[{level}] {title}: {len(items)}")
        for line in items[: args.max_issues]:
            print(f"  - {line}")
        if len(items) > args.max_issues:
            print(f"  - ... {len(items) - args.max_issues} more")
        print("")

    print_group("JSON parse / row type", parse_errors, True)
    print_group("Missing required fields", missing_required, True)
    print_group("Invalid field types", invalid_type, True)
    print_group("Empty required values", empty_required, True)
    print_group("Duplicate instruction", duplicate_instruction, False)
    print_group("Too short instruction", short_instruction, False)
    print_group("Too short output", short_output, False)
    print_group("Too long output", long_output, False)

    errors_total = len(parse_errors) + len(missing_required) + len(invalid_type) + len(empty_required)
    warnings_total = (
        len(duplicate_instruction)
        + len(short_instruction)
        + len(short_output)
        + len(long_output)
    )

    print("Summary:")
    print(f"  errors: {errors_total}")
    print(f"  warnings: {warnings_total}")

    if errors_total > 0:
        return 1
    if args.strict_warn and warnings_total > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
