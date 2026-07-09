#!/usr/bin/env python3
"""Layer 3 — deterministic build & render (Mermaid).

輸入 family_raw.json（§docs/family_raw.schema.json），輸出 Mermaid 家族圖 + 文字摘要。
純確定性、無外部依賴、不打任何 API —— 可離線重跑、可單元測試。

Usage:
    python render_mermaid.py <family_raw.json> [--direction TD|LR] [--max-title N] [--lang en|zh]

Output: Markdown (```mermaid``` block + summary) to stdout.
UI language: --lang en (default) | zh, or set env PATENT_FAMILY_LANG=zh.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from layering import generation_span  # noqa: E402  (shared with render_html)


# ── UI 字串（en 預設 / zh）──────────────────────────────────────────
# 只翻「使用者看得到的輸出」；# 開發註解維持原文。
STR = {
    "en": {
        "unexp": "⋯ not expanded",
        "not_granted": "— not granted —",
        "omitted": "+{n} not expanded⋯",
        "same_family": "same family",
        "sum_head": "## Family summary",
        "root": "- **Root**: {root}",
        "count": "- **Applications**: {total}; **generations**: {span}",
        "gen_span": "{lo} … {hi} ({cnt} generations)",
        "status": "- **Status**: {line}",
        "cip": "- **CIP break points (new matter added, ⚠️ different priority date)**: {parts}",
        "merge": "- **DAG merges (multiple parents)**: {parts}",
        "claims": "{c} claims {n} parent(s) ({ps})",
        "boundary": "- **⚠️ Un-expanded boundary nodes** (hit a cap or fetch failed): {shown}",
        "trunc": {
            "rate-limit": "⚠️ **INCOMPLETE** — hit a USPTO rate limit (429) partway; some branches were not fetched; retry shortly.",
            "time-budget": "⚠️ **INCOMPLETE** — hit the time budget; partial results returned; lower max_nodes or retry (a warm cache speeds it up).",
            "depth-cap": "⚠️ Hit max_depth; deeper generations were not expanded (raise max_depth to see more).",
            "node-cap": "⚠️ Hit the node cap; some neighbours are shown as “+N not expanded” (raise max_nodes to see more).",
            "_default": "⚠️ This graph hit a limit and may be incomplete.",
        },
        "sep": "; ",
        "sep2": ", ",
    },
    "zh": {
        "unexp": "⋯未展開",
        "not_granted": "— 未領證 —",
        "omitted": "+{n} 未展開⋯",
        "same_family": "同族",
        "sum_head": "## 家族摘要",
        "root": "- **起點（root）**：{root}",
        "count": "- **案件數**：{total} 件；**世代**：{span}",
        "gen_span": "{lo} … {hi}（共 {cnt} 代）",
        "status": "- **狀態分布**：{line}",
        "cip": "- **CIP 斷點（新增技術內容處，⚠️ 優先權日不同）**：{parts}",
        "merge": "- **DAG 匯合（多母案）**：{parts}",
        "claims": "{c} 主張 {n} 個母案（{ps}）",
        "boundary": "- **⚠️ 未展開的邊界節點**（碰上限或抓取失敗）：{shown}",
        "trunc": {
            "rate-limit": "⚠️ **不完整** — 中途撞 USPTO 速率限制(429)，部分分支未抓；稍候重試。",
            "time-budget": "⚠️ **不完整** — 達時間預算，回傳部分結果；可調低 max_nodes 或重試（快取會加速）。",
            "depth-cap": "⚠️ 已達 max_depth，較深世代未展開（調高 max_depth 看更多）。",
            "node-cap": "⚠️ 已達節點上限，部分鄰居以「+N 未展開」標示（調高 max_nodes 看更多）。",
            "_default": "⚠️ 本圖已達上限，可能不完整。",
        },
        "sep": "；",
        "sep2": "、",
    },
}


def lang_default() -> str:
    return "zh" if os.environ.get("PATENT_FAMILY_LANG", "").lower().startswith("zh") else "en"


# ── 關係型別正規化 ────────────────────────────────────────────────
# 上游 MCP 已把關係型別正規化成短碼（CON/CIP/DIV/PRO/371/REX/REISSUE）；本函式
# 優先「信任」該短碼直接對應顯示字，再對原始 ODP 文字/fixture 做關鍵字回退。
# 兩個 renderer 共用同一份正規化，避免分歧。未知者「保留原文」而非靜默吞掉。
_SHORT_DISPLAY = {
    "CON": "Continuation", "CIP": "CIP", "DIV": "Division", "PRO": "provisional",
    "371": "371", "REX": "Reexam", "REISSUE": "Reissue",
}


def normalize_rel(raw: str) -> tuple[str, str]:
    s = (raw or "").strip()
    if not s:
        return ("UNKNOWN", "?")
    su = s.upper()
    if su in _SHORT_DISPLAY:  # trust the MCP-normalized short code
        return (su, _SHORT_DISPLAY[su])
    if "CIP" in su or "IN PART" in su or "IN-PART" in su:
        return ("CIP", "CIP")
    if "DIV" in su:
        return ("DIV", "Division")
    if "PROVISIONAL" in su:
        return ("PRO", "provisional")
    if "371" in su or "NATIONAL" in su or "NST" in su:
        return ("371", "371")
    if "REISSUE" in su:
        return ("REISSUE", "Reissue")
    if "REEXAM" in su:
        return ("REX", "Reexam")
    if "CON" in su or "CONTINUATION" in su:  # 放最後：CIP 已先攔截
        return ("CON", "Continuation")
    return ("UNKNOWN", s)  # 保留原文


# ── Mermaid 安全處理 ──────────────────────────────────────────────
def node_id(app_no: str, used: dict[str, str]) -> str:
    """把申請號（含 / , 空白）轉成合法且唯一的 Mermaid 節點 id。"""
    if app_no in used:
        return used[app_no]
    base = "n" + re.sub(r"[^0-9A-Za-z]", "_", app_no)
    nid, i = base, 1
    while nid in used.values():
        i += 1
        nid = f"{base}_{i}"
    used[app_no] = nid
    return nid


def esc(text: str) -> str:
    """轉義會炸掉 Mermaid label 的字元（"、#），保留 <br/> 為換行。"""
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace('"', "&quot;").replace("#", "#35;")


def trunc(text: str | None, n: int) -> str:
    if not text:
        return ""
    text = text.strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def node_label(node: dict[str, Any], is_root: bool, max_title: int, lang: str = "en") -> str:
    s = STR[lang]
    app = node.get("applicationNumberText", "?")
    if not node.get("_fetched", True):
        return esc(app) + "<br/>" + s["unexp"]
    lines = [esc(app)]
    pat = node.get("patentNumber")
    if pat:
        lines.append(esc(pat))
    elif node.get("status") == "provisional":
        lines.append("PROVISIONAL")
    else:
        lines.append(s["not_granted"])
    if node.get("filingDate"):
        lines.append(esc(node["filingDate"]))
    title = trunc(node.get("inventionTitle"), max_title)
    if title:
        lines.append(esc(title))
    if node.get("_omitted"):
        lines.append(s["omitted"].format(n=node["_omitted"]))
    label = "<br/>".join(lines)
    if is_root:
        label = "★ " + label
    return label


# ── 狀態樣式 ──────────────────────────────────────────────────────
STATUS_CLASSDEF = {
    "granted":     "classDef granted fill:#e6f4ea,stroke:#137333,color:#0b3d1f;",
    "pending":     "classDef pending fill:#ffffff,stroke:#999999,stroke-dasharray:4 3,color:#333;",
    "abandoned":   "classDef abandoned fill:#9aa0a6,stroke:#70757c,color:#ffffff;",
    "provisional": "classDef provisional fill:#fff4e5,stroke:#c26401,color:#7a3d00;",
    "unknown":     "classDef unknown fill:#eef0f2,stroke:#c0c4c9,stroke-dasharray:2 3,color:#6a6f76;",
}
KNOWN_STATUS = set(STATUS_CLASSDEF)


def render(data: dict[str, Any], direction: str = "TD", max_title: int = 30, lang: str = "en") -> str:
    s = STR[lang]
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    root = data.get("root")
    overlay = data.get("overlay", {}) or {}

    by_app = {n.get("applicationNumberText"): n for n in nodes}
    used: dict[str, str] = {}

    lines: list[str] = [f"flowchart {direction}"]

    # 節點
    for n in nodes:
        app = n.get("applicationNumberText")
        nid = node_id(app, used)
        is_root = app == root
        label = node_label(n, is_root, max_title, lang)
        lines.append(f'    {nid}["{label}"]')

    # 邊（含關係型別標籤）
    for e in edges:
        f, t = e.get("from"), e.get("to")
        if f not in by_app or t not in by_app:
            continue  # Layer 1 應保證，但防禦性略過懸空邊
        fid, tid = node_id(f, used), node_id(t, used)
        _, disp = normalize_rel(e.get("relationshipType") or e.get("rawTypeCode", ""))
        lines.append(f"    {fid} -->|{esc(disp)}| {tid}")

    lines.append("")

    # 狀態 class 指派
    status_groups: dict[str, list[str]] = {}
    for n in nodes:
        st = n.get("status") if n.get("status") in KNOWN_STATUS else "unknown"
        status_groups.setdefault(st, []).append(node_id(n.get("applicationNumberText"), used))
    for st in sorted(status_groups):
        lines.append("    " + STATUS_CLASSDEF[st])
    for st in sorted(status_groups):
        lines.append(f"    class {','.join(status_groups[st])} {st};")

    # root 加粗外框（疊在 status 樣式之上）
    if root in by_app:
        lines.append(f"    style {node_id(root, used)} stroke-width:4px,stroke:#111111;")

    # overlay：INPADOC 跨國對應案徽章（旁掛虛線）
    for app, ov in overlay.items():
        if app not in by_app:
            continue
        members = ov.get("members", [])
        if not members:
            continue
        bid = node_id(app, used) + "_intl"
        shown = ", ".join(members[:4]) + ("…" if len(members) > 4 else "")
        fam = ov.get("inpadocFamilyId")
        head = f"🌐 INPADOC {esc(fam)}" if fam else "🌐 INPADOC"
        lines.append(f'    {bid}["{head}<br/>{esc(shown)}"]')
        lines.append(f"    classDef intl fill:#eef2ff,stroke:#3b5bdb,color:#1e3a8a,stroke-dasharray:3 2;")
        lines.append(f"    class {bid} intl;")
        lines.append(f"    {node_id(app, used)} -.-|{s['same_family']}| {bid}")

    return "\n".join(lines)


# ── 文字摘要 ──────────────────────────────────────────────────────
def summarize(data: dict[str, Any], lang: str = "en") -> str:
    s = STR[lang]
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    root = data.get("root")
    by_app = {n.get("applicationNumberText"): n for n in nodes}

    total = len(nodes)
    st_count: dict[str, int] = {}
    for n in nodes:
        st_count[n.get("status", "unknown")] = st_count.get(n.get("status", "unknown"), 0) + 1

    # 世代用拓撲分層計算（非 _depth，後者在 DAG 會被跨代優先權邊拉平）
    if nodes:
        lo, hi, cnt = generation_span(nodes, edges, root)
        gen_span = s["gen_span"].format(lo=lo, hi=hi, cnt=cnt)
    else:
        gen_span = "n/a"

    # 多母案（DAG 匯合）：同一 child 有 >1 條入邊
    parents_of: dict[str, list[str]] = {}
    for e in edges:
        parents_of.setdefault(e.get("to"), []).append(e.get("from"))
    merges = {c: ps for c, ps in parents_of.items() if len(ps) > 1}

    # CIP 斷點
    cips = [e for e in edges if normalize_rel(e.get("relationshipType") or e.get("rawTypeCode", ""))[0] == "CIP"]

    unexpanded = [n.get("applicationNumberText") for n in nodes if not n.get("_fetched", True)]

    out: list[str] = []
    out.append(s["sum_head"])
    out.append(s["root"].format(root=root))
    out.append(s["count"].format(total=total, span=gen_span))
    status_line = s["sep2"].join(f"{k} {v}" for k, v in sorted(st_count.items()))
    out.append(s["status"].format(line=status_line))
    if cips:
        parts = []
        for e in cips:
            child = by_app.get(e.get("to"), {})
            pat = child.get("patentNumber") or child.get("applicationNumberText")
            parts.append(f"{e.get('from')} →(CIP) {pat}")
        out.append(s["cip"].format(parts=s["sep"].join(parts)))
    if merges:
        parts = [s["claims"].format(c=c, n=len(ps), ps=", ".join(ps)) for c, ps in merges.items()]
        out.append(s["merge"].format(parts=s["sep"].join(parts)))
    if unexpanded:
        shown = ", ".join(unexpanded[:12]) + ("…" if len(unexpanded) > 12 else "")
        out.append(s["boundary"].format(shown=shown))
    if data.get("truncated"):
        reason = data.get("truncationReason")
        msg = s["trunc"].get(reason, s["trunc"]["_default"])
        out.append(f"- **{msg}**")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="family_raw.json → Mermaid family graph + summary")
    ap.add_argument("input", help="path to family_raw.json")
    ap.add_argument("--direction", default="TD", choices=["TD", "LR"], help="graph direction (default TD)")
    ap.add_argument("--max-title", type=int, default=30, help="title truncation length (default 30)")
    ap.add_argument("--lang", default=lang_default(), choices=["en", "zh"],
                    help="UI language (default: en, or env PATENT_FAMILY_LANG)")
    args = ap.parse_args(argv)

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    from validate import validate_family_raw
    problems = validate_family_raw(data)
    if problems:
        print("⚠️ family_raw contract-validation warnings:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)

    print("```mermaid")
    print(render(data, direction=args.direction, max_title=args.max_title, lang=args.lang))
    print("```")
    print()
    print(summarize(data, lang=args.lang))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
