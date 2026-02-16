#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


WORD_RE = re.compile(r"[A-Za-z0-9_]+")
TOKEN_SPLIT_RE = re.compile(r"[\s,，。！？、;；:：()（）\[\]{}<>《》\"'`]+")

REWRITE_RULES: list[tuple[str, list[str]]] = [
    ("受到伤害", ["受伤后", "伤害后", "damageAfter", "damageEnd", "damage"]),
    ("收到伤害", ["受到伤害", "受伤后", "伤害后", "damageAfter", "damageEnd", "damage"]),
    ("受伤", ["受到伤害", "伤害后", "damageAfter", "damage"]),
    ("伤害", ["damage", "damageAfter", "damageEnd"]),
    ("摸牌", ["摸一张牌", "draw", "drawCards"]),
    ("弃牌", ["弃置", "discard", "chooseToDiscard"]),
    ("回复体力", ["回复", "recover", "recoverEnd"]),
    ("回复", ["回复体力", "recover"]),
    ("体力变化", ["changeHp", "changeHpAfter"]),
    ("失去体力", ["loseHp", "loseHpAfter"]),
    ("使用杀", ["使用【杀】", "sha", "useCard"]),
    ("杀", ["【杀】", "sha"]),
]

TRIGGER_HINTS: dict[str, list[str]] = {
    "damage": ["受到伤害", "收到伤害", "受伤", "伤害后", "damageAfter", "damageEnd", "damage"],
    "hp_change": ["体力变化", "changeHp", "changeHpAfter"],
    "lose_hp": ["失去体力", "loseHp", "loseHpAfter"],
    "use_card": ["使用牌", "useCard", "useCard1", "useCard2"],
}

EFFECT_HINTS: dict[str, list[str]] = {
    "draw": ["摸牌", "摸一张牌", "draw", "drawCards"],
    "discard": ["弃牌", "弃置", "discard", "chooseToDiscard"],
    "recover": ["回复", "回复体力", "recover", "recoverEnd"],
    "damage": ["造成伤害", "damage", "damageBegin", "damageEnd"],
    "gain_card": ["获得牌", "gain", "gainPlayerCard"],
}

STOP_PHRASES = [
    "请帮我",
    "帮我",
    "请",
    "我要",
    "我想",
    "写一个",
    "写个",
    "做一个",
    "做个",
    "实现",
    "技能",
    "的技能",
]


def default_dataset_path() -> Path:
    # scripts/search_dataset.py -> skill_root/assets/dataset.jsonl
    return Path(__file__).resolve().parents[1] / "assets" / "dataset.jsonl"


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def tokenize(text: str) -> set[str]:
    text = normalize(text)
    parts = {p for p in TOKEN_SPLIT_RE.split(text) if len(p) >= 2}
    words = {w for w in WORD_RE.findall(text) if len(w) >= 2}

    hinted: set[str] = set()
    for source, alts in REWRITE_RULES:
        if source in text:
            hinted.add(source)
        for alt in alts:
            if alt in text and len(alt) >= 2:
                hinted.add(alt)

    return parts | words | hinted


def snippet(text: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def unique_preserve(items: list[str], max_count: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        value = normalize(item)
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(item.strip())
        if len(out) >= max_count:
            break
    return out


def contains_any(text: str, values: list[str]) -> bool:
    return any(v in text for v in values)


def simplify_query(query: str) -> str:
    result = query
    for phrase in STOP_PHRASES:
        result = result.replace(phrase, " ")
    result = re.sub(r"[，。！？、,.!?]", " ", result)
    return normalize(result)


def expand_query_routes(query: str, max_routes: int) -> list[str]:
    routes: list[str] = [query]
    query_norm = normalize(query)

    simplified = simplify_query(query)
    if simplified and simplified != query_norm:
        routes.append(simplified)

    for source, alts in REWRITE_RULES:
        if source in query:
            for alt in alts:
                routes.append(query.replace(source, alt))
                if simplified:
                    routes.append(f"{simplified} {alt}")

    detected_trigger_groups: list[str] = []
    detected_effect_groups: list[str] = []
    for group_name, hints in TRIGGER_HINTS.items():
        if contains_any(query, hints):
            detected_trigger_groups.append(group_name)
    for group_name, hints in EFFECT_HINTS.items():
        if contains_any(query, hints):
            detected_effect_groups.append(group_name)

    trigger_terms: list[str] = []
    effect_terms: list[str] = []
    for group_name in detected_trigger_groups:
        trigger_terms.extend(TRIGGER_HINTS[group_name][:3])
    for group_name in detected_effect_groups:
        effect_terms.extend(EFFECT_HINTS[group_name][:3])

    if trigger_terms and effect_terms:
        for t in trigger_terms[:4]:
            for e in effect_terms[:4]:
                routes.append(f"{t} {e}")
                routes.append(f"{e} {t}")
    else:
        for term in trigger_terms[:6]:
            routes.append(term)
        for term in effect_terms[:6]:
            routes.append(term)

    if simplified:
        routes.append(f"{simplified} trigger filter content")

    return unique_preserve(routes, max_count=max_routes)


def parse_routes_from_text(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []

    # Accept either ["..."] or {"routes":["..."]}.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(x) for x in parsed if isinstance(x, str)]
        if isinstance(parsed, dict) and isinstance(parsed.get("routes"), list):
            return [str(x) for x in parsed["routes"] if isinstance(x, str)]
    except json.JSONDecodeError:
        pass

    # Fallback: find first JSON array substring.
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        return []
    try:
        parsed = json.loads(m.group(0))
        if isinstance(parsed, list):
            return [str(x) for x in parsed if isinstance(x, str)]
    except json.JSONDecodeError:
        return []
    return []


def call_openai_rewriter(
    query: str,
    max_routes: int,
    model: str,
    api_key: str,
    base_url: str,
    timeout_sec: int,
) -> list[str]:
    endpoint = base_url.rstrip("/") + "/chat/completions"
    system_prompt = (
        "你是无名杀技能检索改写器。"
        "输入是一个自然语言技能需求。"
        "输出只允许 JSON，返回一个字符串数组 routes，包含 6-12 条短检索词。"
        "规则：保留原意；加入触发时机词（如 受到伤害/伤害后/damageEnd/damageAfter）；"
        "加入效果词（如 摸牌/draw）；加入无名杀代码常见词（trigger/filter/content/useCard/phase）；"
        "每条尽量短；不要解释。"
    )
    user_prompt = (
        f"需求：{query}\n"
        f"最多 {max_routes} 条。\n"
        "请返回格式：{\"routes\":[\"...\",\"...\"]}"
    )

    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    data = json.loads(body)
    content = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    routes = parse_routes_from_text(content)
    return unique_preserve(routes, max_count=max_routes)


def build_routes(
    query: str,
    rewrite_mode: str,
    max_routes: int,
    llm_model: str,
    llm_base_url: str,
    llm_timeout: int,
    llm_api_key: str | None,
) -> tuple[list[str], str]:
    if rewrite_mode == "rule":
        return expand_query_routes(query, max_routes=max_routes), "rule"

    if rewrite_mode in {"llm", "auto"}:
        if not llm_api_key:
            if rewrite_mode == "llm":
                raise SystemExit("LLM rewrite requires OPENAI_API_KEY or --llm-api-key.")
            return expand_query_routes(query, max_routes=max_routes), "rule-fallback(no-api-key)"
        try:
            routes = call_openai_rewriter(
                query=query,
                max_routes=max_routes,
                model=llm_model,
                api_key=llm_api_key,
                base_url=llm_base_url,
                timeout_sec=llm_timeout,
            )
            if routes:
                # Keep original query in front for stability.
                merged = unique_preserve([query] + routes, max_count=max_routes)
                return merged, "llm"
            if rewrite_mode == "llm":
                raise SystemExit("LLM rewrite returned no routes.")
            return expand_query_routes(query, max_routes=max_routes), "rule-fallback(empty-llm)"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            if rewrite_mode == "llm":
                raise SystemExit(f"LLM rewrite failed: {e}")
            return expand_query_routes(query, max_routes=max_routes), "rule-fallback(llm-error)"

    raise SystemExit(f"Unknown rewrite mode: {rewrite_mode}")


def score_row(query_norm: str, query_tokens: set[str], row: dict[str, Any]) -> float:
    instruction = str(row.get("instruction", ""))
    model_input = str(row.get("input", ""))
    output = str(row.get("output", ""))

    searchable = normalize(f"{instruction}\n{model_input}")
    score = 0.0

    if query_norm and query_norm in searchable:
        score += 10.0

    row_tokens = tokenize(searchable)
    score += 1.6 * len(query_tokens & row_tokens)

    output_norm = normalize(output)
    output_overlap = len(query_tokens & tokenize(output_norm))
    score += 0.35 * output_overlap

    return score


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                row["_line"] = i
                rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Search noname skill dataset.jsonl with query rewriting and return best matches."
    )
    parser.add_argument("--query", required=True, help="Search query, e.g. '锁定技 体力变化 蓄力'")
    parser.add_argument("--dataset", default=str(default_dataset_path()), help="Path to dataset.jsonl")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results to return")
    parser.add_argument("--max-routes", type=int, default=10, help="Max rewritten query routes")
    parser.add_argument(
        "--rewrite-mode",
        choices=["auto", "rule", "llm"],
        default="auto",
        help="Route rewrite mode: auto (prefer LLM), rule, llm (strict).",
    )
    parser.add_argument("--llm-model", default="gpt-4.1-mini", help="OpenAI model for LLM rewriting")
    parser.add_argument(
        "--llm-base-url",
        default=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        help="OpenAI API base URL",
    )
    parser.add_argument("--llm-timeout", type=int, default=30, help="LLM request timeout seconds")
    parser.add_argument("--llm-api-key", default=os.getenv("OPENAI_API_KEY", ""), help="OpenAI API key")
    parser.add_argument(
        "--multi-route",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable multi-route query rewriting",
    )
    parser.add_argument("--show-routes", action="store_true", help="Print rewritten query routes")
    parser.add_argument(
        "--output-limit",
        type=int,
        default=500,
        help="Max chars shown for output code when not using --full-output",
    )
    parser.add_argument("--full-output", action="store_true", help="Print full output code")
    parser.add_argument("--json", action="store_true", help="Print results as JSON")
    args = parser.parse_args()

    dataset_path = Path(args.dataset).resolve()
    if not dataset_path.exists():
        raise SystemExit(f"Dataset file not found: {dataset_path}")

    rows = load_jsonl(dataset_path)
    if args.multi_route:
        routes, route_mode_used = build_routes(
            query=args.query,
            rewrite_mode=args.rewrite_mode,
            max_routes=max(args.max_routes, 1),
            llm_model=args.llm_model,
            llm_base_url=args.llm_base_url,
            llm_timeout=args.llm_timeout,
            llm_api_key=args.llm_api_key,
        )
    else:
        routes = [args.query]
        route_mode_used = "disabled"
    route_features = [(route, normalize(route), tokenize(route)) for route in routes]

    scored: list[tuple[float, dict[str, Any], str]] = []
    for row in rows:
        best_score = 0.0
        best_route = ""
        for route, route_norm, route_tokens in route_features:
            score = score_row(route_norm, route_tokens, row)
            if score > best_score:
                best_score = score
                best_route = route
        if best_score > 0:
            scored.append((best_score, row, best_route))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[: max(args.top_k, 1)]

    if args.json:
        payload = []
        for score, row, matched_route in top:
            output = str(row.get("output", ""))
            payload.append(
                {
                    "score": round(score, 4),
                    "line": row.get("_line"),
                    "route_mode_used": route_mode_used,
                    "matched_route": matched_route,
                    "instruction": row.get("instruction", ""),
                    "input": row.get("input", ""),
                    "output": output if args.full_output else snippet(output, args.output_limit),
                }
            )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if not top:
        print("No matched rows.")
        return 0

    print(f"Dataset: {dataset_path}")
    print(f"Total rows: {len(rows)}")
    print(f"Query: {args.query}")
    print(f"Route mode: {route_mode_used}")
    print(f"Routes: {len(routes)}")
    print(f"Matched: {len(scored)}")
    print("")

    if args.show_routes:
        print("Rewritten routes:")
        for i, route in enumerate(routes, start=1):
            print(f"  {i}. {route}")
        print("")

    for idx, (score, row, matched_route) in enumerate(top, start=1):
        instruction = str(row.get("instruction", ""))
        model_input = str(row.get("input", ""))
        output = str(row.get("output", ""))

        print(f"[{idx}] score={score:.2f} line={row.get('_line')}")
        print(f"matched_route: {matched_route}")
        print(f"instruction: {instruction}")
        if model_input:
            print(f"input: {model_input}")
        print("output:")
        print(output if args.full_output else snippet(output, args.output_limit))
        print("-" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
