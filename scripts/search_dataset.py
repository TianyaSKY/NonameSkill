#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import math
import os
import re
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


WORD_RE = re.compile(r"[A-Za-z0-9_]+")
TOKEN_SPLIT_RE = re.compile(r"[\s,，。！？、;；:：()（）\[\]{}<>《》\"'`]+")
CJK_BLOCK_RE = re.compile(r"[\u4e00-\u9fff]+")
CJK_SINGLE_RE = re.compile(r"^[\u4e00-\u9fff]$")

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
    "damage": ["受到伤害", "收到伤害", "受伤", "伤害", "伤害后", "damageAfter", "damageEnd", "damage"],
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

_SIMPLE_NORM = lambda s: re.sub(r"\s+", " ", s).strip().lower()
DAMAGE_HINT_TOKENS = {_SIMPLE_NORM(t) for t in TRIGGER_HINTS["damage"]}
DRAW_HINT_TOKENS = {_SIMPLE_NORM(t) for t in EFFECT_HINTS["draw"]}
DAMAGE_TO_DRAW_RE = re.compile(r"(受到伤害后|收到伤害后|受伤后|伤害后)[^。；;]{0,28}(摸|draw)")

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

LOW_SIGNAL_TOKENS = {
    "技能",
    "实现",
    "做一个",
    "做个",
    "写一个",
    "写个",
    "一个",
    "trigger",
    "filter",
    "content",
}


def default_sqlite_path() -> Path:
    # scripts/search_dataset.py -> skill_root/assets/dataset.sqlite3
    return Path(__file__).resolve().parents[1] / "assets" / "dataset.sqlite3"


def default_card_sqlite_path() -> Path:
    # scripts/search_dataset.py -> skill_root/assets/card_code_effect_dataset.sqlite3
    return Path(__file__).resolve().parents[1] / "assets" / "card_code_effect_dataset.sqlite3"


@dataclasses.dataclass
class RowFeatures:
    row: dict[str, Any]
    instruction_norm: str
    input_norm: str
    output_norm: str
    instruction_tokens: set[str]
    input_tokens: set[str]
    output_tokens: set[str]
    all_tokens: set[str]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def extract_index_terms(text: str) -> set[str]:
    text_norm = normalize(text)
    terms: set[str] = set()

    for token in TOKEN_SPLIT_RE.split(text_norm):
        if (2 <= len(token) <= 48 or (len(token) == 1 and CJK_SINGLE_RE.fullmatch(token))) and token not in LOW_SIGNAL_TOKENS:
            terms.add(token)

    for token in WORD_RE.findall(text_norm):
        if 2 <= len(token) <= 48 and token not in LOW_SIGNAL_TOKENS:
            terms.add(token)

    # Add CJK n-grams so phrase queries like "受到伤害后 摸牌" can be matched efficiently in FTS.
    for block in CJK_BLOCK_RE.findall(text_norm):
        block_len = len(block)
        if 2 <= block_len <= 24:
            terms.add(block)
        for n in (2, 3, 4):
            if block_len < n:
                continue
            for i in range(block_len - n + 1):
                terms.add(block[i : i + n])

    return terms


def tokenize(text: str, *, expand_hints: bool = False) -> set[str]:
    text = normalize(text)
    parts = {
        p
        for p in TOKEN_SPLIT_RE.split(text)
        if (len(p) >= 2 or (len(p) == 1 and CJK_SINGLE_RE.fullmatch(p)))
    }
    words = {w for w in WORD_RE.findall(text) if len(w) >= 2}

    if not expand_hints:
        return parts | words

    hinted: set[str] = set()
    for source, alts in REWRITE_RULES:
        if source in text:
            hinted.add(source)
            hinted.update(alt for alt in alts if len(alt) >= 2)

    return parts | words | hinted


def filter_query_tokens(tokens: set[str]) -> set[str]:
    filtered = {t for t in tokens if t not in LOW_SIGNAL_TOKENS}
    return filtered or tokens


def snippet(text: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def normalize_route_text(route: str) -> str:
    route = re.sub(r"(后){2,}", "后", route)
    route = re.sub(r"\s+", " ", route).strip()
    return route


def safe_replace_route(query: str, source: str, alt: str) -> str:
    pattern = re.escape(source)
    # Avoid artifacts like "伤害后后" and "damageAfter后".
    if not source.endswith("后") and (alt.endswith("后") or WORD_RE.fullmatch(alt)):
        pattern = re.escape(source) + r"(?!后)"
    return normalize_route_text(re.sub(pattern, alt, query))


def unique_preserve(items: list[str], max_count: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        item = normalize_route_text(item)
        value = normalize(item)
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(item)
        if len(out) >= max_count:
            break
    return out


def contains_any(text: str, values: list[str]) -> bool:
    return any(v in text for v in values)


def collect_required_tokens(text_norm: str, groups: dict[str, list[str]]) -> set[str]:
    required: set[str] = set()
    for hints in groups.values():
        if any(normalize(h) in text_norm for h in hints):
            required.update(normalize(h) for h in hints if len(normalize(h)) >= 2)
    return required


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
                routes.append(safe_replace_route(query, source, alt))
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


def min_required_overlap(query_tokens: set[str], manual_min_overlap: int) -> int:
    if manual_min_overlap > 0:
        return manual_min_overlap
    n = len(query_tokens)
    if n <= 1:
        return 1
    if n <= 4:
        return 2
    return max(2, math.ceil(n * 0.45))


def build_feature_index(rows: list[dict[str, Any]]) -> tuple[list[RowFeatures], dict[str, float]]:
    features: list[RowFeatures] = []
    df: collections.Counter[str] = collections.Counter()
    for row in rows:
        instruction_norm = normalize(str(row.get("instruction", "")))
        input_norm = normalize(str(row.get("input", "")))
        output_norm = normalize(str(row.get("output", "")))
        instruction_tokens = tokenize(instruction_norm, expand_hints=False)
        input_tokens = tokenize(input_norm, expand_hints=False)
        output_tokens = tokenize(output_norm, expand_hints=False)
        all_tokens = instruction_tokens | input_tokens | output_tokens
        features.append(
            RowFeatures(
                row=row,
                instruction_norm=instruction_norm,
                input_norm=input_norm,
                output_norm=output_norm,
                instruction_tokens=instruction_tokens,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                all_tokens=all_tokens,
            )
        )
        for token in all_tokens:
            df[token] += 1

    n_docs = max(1, len(features))
    idf: dict[str, float] = {}
    for token, freq in df.items():
        # BM25-like IDF, but simplified for this script.
        idf[token] = math.log((n_docs + 1) / (freq + 0.5)) + 1.0
    return features, idf


def weighted_overlap(query_tokens: set[str], field_tokens: set[str], token_idf: dict[str, float]) -> float:
    return sum(token_idf.get(token, 1.0) for token in query_tokens if token in field_tokens)


def score_row(
    query_norm: str,
    query_tokens: set[str],
    rowf: RowFeatures,
    token_idf: dict[str, float],
    min_overlap: int,
    required_trigger_tokens: set[str],
    required_effect_tokens: set[str],
) -> float:
    row_text = f"{rowf.instruction_norm} {rowf.input_norm} {rowf.output_norm}"
    if required_trigger_tokens and not any(t in row_text for t in required_trigger_tokens):
        return 0.0
    if required_effect_tokens and not any(t in row_text for t in required_effect_tokens):
        return 0.0

    overlap_tokens = query_tokens & rowf.all_tokens
    has_exact_match = bool(
        query_norm
        and (
            query_norm in rowf.instruction_norm
            or query_norm in rowf.input_norm
            or query_norm in rowf.output_norm
        )
    )
    if not has_exact_match and len(overlap_tokens) < min_overlap:
        return 0.0

    score = 0.0
    if query_norm:
        if query_norm in rowf.instruction_norm:
            score += 14.0
        elif query_norm in rowf.input_norm:
            score += 6.0
        elif query_norm in rowf.output_norm:
            score += 2.0

    score += 2.8 * weighted_overlap(query_tokens, rowf.instruction_tokens, token_idf)
    score += 1.2 * weighted_overlap(query_tokens, rowf.input_tokens, token_idf)
    score += 0.45 * weighted_overlap(query_tokens, rowf.output_tokens, token_idf)

    has_damage_intent = bool(required_trigger_tokens & DAMAGE_HINT_TOKENS)
    has_draw_intent = bool(required_effect_tokens & DRAW_HINT_TOKENS)
    if has_damage_intent and has_draw_intent:
        if DAMAGE_TO_DRAW_RE.search(rowf.instruction_norm):
            score += 12.0
        elif (
            ("受到伤害后" in rowf.instruction_norm or "收到伤害后" in rowf.instruction_norm or "受伤后" in rowf.instruction_norm)
            and ("摸牌" in rowf.instruction_norm or "摸一张牌" in rowf.instruction_norm)
        ):
            score += 6.0

    if len(overlap_tokens) >= (min_overlap + 2):
        score += 1.5

    return score


def sql_escape_fts_token(token: str) -> str:
    return token.replace('"', '""')


def make_fts_query_from_route(route: str) -> str:
    terms = sorted(extract_index_terms(route))
    if not terms:
        return ""
    # OR for recall; rerank happens in Python scoring.
    return " OR ".join(f'"{sql_escape_fts_token(term)}"' for term in terms[:40])


def load_candidates_from_sqlite(
    sqlite_path: Path,
    routes: list[str],
    candidate_pool: int,
) -> list[dict[str, Any]]:
    per_route = max(80, candidate_pool // max(len(routes), 1))
    rows_by_line: dict[int, dict[str, Any]] = {}

    with sqlite3.connect(str(sqlite_path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        for route in routes:
            match_query = make_fts_query_from_route(route)
            if not match_query:
                continue
            try:
                cur.execute(
                    """
                    SELECT s.line, s.instruction, s.input, s.output
                    FROM skills_fts
                    JOIN skills s ON s.id = skills_fts.rowid
                    WHERE skills_fts MATCH ?
                    ORDER BY bm25(skills_fts)
                    LIMIT ?
                    """,
                    (match_query, per_route),
                )
                fetched = cur.fetchall()
            except sqlite3.Error:
                fetched = []

            for item in fetched:
                line = int(item["line"])
                if line in rows_by_line:
                    continue
                rows_by_line[line] = {
                    "_line": line,
                    "instruction": item["instruction"] or "",
                    "input": item["input"] or "",
                    "output": item["output"] or "",
                }
                if len(rows_by_line) >= candidate_pool:
                    break

            if len(rows_by_line) >= candidate_pool:
                break

    return list(rows_by_line.values())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Search noname skill/card sqlite dataset with query rewriting and return best matches."
    )
    parser.add_argument("--query", required=True, help="Search query, e.g. '锁定技 体力变化 蓄力'")
    parser.add_argument(
        "--dataset-kind",
        choices=["skill", "card"],
        default="skill",
        help="Preset dataset profile. skill=skills dataset, card=card code/effect dataset.",
    )
    parser.add_argument("--sqlite-path", default="", help="Path to dataset.sqlite3 (optional override)")
    parser.add_argument(
        "--candidate-pool",
        type=int,
        default=1200,
        help="Max candidate rows loaded from sqlite before rerank.",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Number of results to return")
    parser.add_argument("--max-routes", type=int, default=10, help="Max rewritten query routes")
    parser.add_argument(
        "--min-overlap",
        type=int,
        default=0,
        help="Minimum overlapped query tokens per row. 0 means auto threshold.",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="Minimum final score required to keep a row.",
    )
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

    if args.sqlite_path:
        sqlite_path = Path(args.sqlite_path).resolve()
    else:
        sqlite_path = (
            default_card_sqlite_path().resolve()
            if args.dataset_kind == "card"
            else default_sqlite_path().resolve()
        )
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

    search_engine = "sqlite"
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite index file not found: {sqlite_path}")
    rows = load_candidates_from_sqlite(
        sqlite_path=sqlite_path,
        routes=routes,
        candidate_pool=max(200, args.candidate_pool),
    )
    if not rows:
        print("No matched rows.")
        return 0

    row_features, token_idf = build_feature_index(rows)
    effective_min_overlap = args.min_overlap
    if effective_min_overlap <= 0 and args.dataset_kind == "card":
        effective_min_overlap = 1

    route_features = []
    for route in routes:
        route_norm = normalize(route)
        route_base_tokens = filter_query_tokens(tokenize(route, expand_hints=False))
        route_tokens = filter_query_tokens(tokenize(route, expand_hints=True))
        route_min_overlap = min_required_overlap(route_base_tokens, effective_min_overlap)
        required_trigger_tokens = collect_required_tokens(route_norm, TRIGGER_HINTS)
        required_effect_tokens = collect_required_tokens(route_norm, EFFECT_HINTS)
        route_features.append(
            (
                route,
                route_norm,
                route_tokens,
                route_min_overlap,
                required_trigger_tokens,
                required_effect_tokens,
            )
        )

    scored: list[tuple[float, RowFeatures, str]] = []
    for rowf in row_features:
        best_score = 0.0
        best_route = ""
        for (
            route,
            route_norm,
            route_tokens,
            route_min_overlap,
            required_trigger_tokens,
            required_effect_tokens,
        ) in route_features:
            score = score_row(
                query_norm=route_norm,
                query_tokens=route_tokens,
                rowf=rowf,
                token_idf=token_idf,
                min_overlap=route_min_overlap,
                required_trigger_tokens=required_trigger_tokens,
                required_effect_tokens=required_effect_tokens,
            )
            if score > best_score:
                best_score = score
                best_route = route
        if best_score >= args.min_score and best_score > 0:
            scored.append((best_score, rowf, best_route))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[: max(args.top_k, 1)]

    if args.json:
        payload = []
        for score, rowf, matched_route in top:
            row = rowf.row
            output = str(row.get("output", ""))
            payload.append(
                {
                    "score": round(score, 4),
                    "line": row.get("_line"),
                    "search_engine": search_engine,
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

    print(f"Search engine: {search_engine}")
    print(f"SQLite index: {sqlite_path}")
    print(f"Candidate rows: {len(rows)}")
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

    for idx, (score, rowf, matched_route) in enumerate(top, start=1):
        row = rowf.row
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
