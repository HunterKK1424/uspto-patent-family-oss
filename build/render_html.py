#!/usr/bin/env python3
"""Layer 3 (HTML) — deterministic family_raw.json → self-contained INTERACTIVE HTML.

Phase B: client-side app — embed analysed data + a JS app that filters /
re-lays-out / re-renders in the browser.
Phase C: adds a YEAR-axis layout (filing-date timeline + year gridlines,
申請→領證 pendency bars, copendency red flags) and a manual 深/淺 theme toggle.

Deterministic ANALYSIS (topological layering, lineage) stays in Python; the JS
only positions & draws. `--svg-only` still emits a static SVG (generation view).

用法:
    python render_html.py <family_raw.json> [-o out.html] [--title "..."]
    python render_html.py <family_raw.json> --svg-only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_mermaid import normalize_rel  # noqa: E402
from layering import assign_layers        # noqa: E402


BOX_W, BOX_H = 168, 60
COL_GAP, ROW_GAP = 196, 140
MARGIN_X, MARGIN_Y = 48, 72

# 著作權宣告（可改）。持有人可用環境變數 PATENT_COPYRIGHT_HOLDER 覆蓋。
COPYRIGHT_HOLDER = os.environ.get("PATENT_COPYRIGHT_HOLDER", "Chun-Yu Yen (Hunter Yen)")
COPYRIGHT_YEAR = os.environ.get("PATENT_COPYRIGHT_YEAR", "2026")


def lang_default() -> str:
    return "zh" if os.environ.get("PATENT_FAMILY_LANG", "").lower().startswith("zh") else "en"


# ── UI 字串（en 預設 / zh）──────────────────────────────────────────
# 只翻「使用者看得到的輸出」；# 開發註解維持原文。JS 端字串經 window.__I18N__ 注入。
STR_HTML = {
    "en": {
        "htmllang": "en",
        "status": {"granted": "granted", "pending": "pending", "abandoned": "abandoned",
                   "provisional": "provisional", "unknown": "unknown"},
        "copyright_notice": "For noncommercial use only (PolyForm Noncommercial 1.0.0). "
                            "Commercial use requires a separate license: hunterip0305@gmail.com",
        "title_default": "US patent family tree — root {root}",
        "sum_cases": "{n} applications, {e} links",
        "sum_status": "status: {parts}",
        "sum_scope": "scope: {scope}",
        "sum_sep": ", ",
        "sum_join": "  |  ",
        "sum_trunc": {"rate-limit": "⚠️ incomplete (429)", "time-budget": "⚠️ incomplete (time)",
                      "depth-cap": "⚠️ depth cap", "node-cap": "⚠️ node cap", "_default": "⚠️ hit a limit"},
        "btn_reset": "⟳ Reset", "btn_dark": "🌙 Dark", "btn_light": "☀ Light",
        "seg_gen": "By generation", "seg_year": "By year",
        "ck_bar": "filing→grant bar", "ck_flag": "copendency flags",
        "count_suffix": "shown",
        "grp_lineal": "Lineage", "tgl_lineal": "Lineal only (hide collateral)",
        "grp_status": "Status", "grp_rel": "Relation", "grp_applicant": "Applicant",
        "grp_down": "Generations down", "all_word": "all", "gen_suffix": "gen",
        "tt_status": "status: ", "tt_filed": "filed ", "tt_granted": "granted ",
        "tt_lineage": "lineage: ",
        "lineage": {"root": "query root", "ancestor": "ancestor (priority chain)",
                    "descendant": "descendant", "collateral": "collateral"},
        "tt_boundary": "(boundary node: not expanded)",
        "tt_omitted": "{n} more related application(s) not expanded",
        "lbl_undated": "undated", "lbl_unexp": "⋯ not expanded", "lbl_notgranted": "— not granted —",
        "disc_flag": "⚠️ Red flag = child's filing date is later than the parent's pendency end "
                     "(grant/abandonment) → possible §120 copendency break; verify each case.",
        "disc_legal": "This shows the as-recorded US continuity, not a perfected chain of legal "
                      "benefit (cf. Natural Alternatives v. Iancu, 904 F.3d 1375); reference only, not legal advice.",
        "foot_flag": "<span class=\"flag-k\">Red flag (copendency warning)</span>: the child's "
                     "<b>filing date</b> is later than the (visible) parent's <b>pendency end date</b> "
                     "(grant or abandonment) → the continuing application may have been filed after the "
                     "parent was no longer pending, and could fail the 35 U.S.C. §120 <b>copendency</b> "
                     "requirement and lose the priority benefit. Heuristic hint; verify each case.",
        "foot_ops": "<b>Controls</b>: click a swatch/label to filter live; “Lineal only” hides "
                    "collateral; “By year” uses the filing date as the Y axis (year bands + zebra "
                    "stripes); hover for full detail; download = current view (with notes; export is "
                    "fixed light, suitable for reports).",
        "foot_disc": "<b>Disclaimer</b>: this shows the <b>as-recorded</b> US continuity (parent/child) "
                     "relationships, <b>not</b> a perfected chain of legal benefit; full specific-reference "
                     "continuity and copendency-break risk must still be checked case by case "
                     "(cf. <i>Natural Alternatives International v. Iancu</i>, 904 F.3d 1375 (Fed. Cir. 2018)). "
                     "It excludes claim-by-claim EFD and Paris Convention foreign priority. For reference "
                     "only, <b>not legal advice</b>. This tool is unofficial and not affiliated with or "
                     "endorsed by the USPTO.",
    },
    "zh": {
        "htmllang": "zh-Hant",
        "status": {"granted": "已領證", "pending": "審查中", "abandoned": "已放棄",
                   "provisional": "臨時案", "unknown": "未知"},
        "copyright_notice": "僅供非商業使用 (PolyForm Noncommercial 1.0.0)。"
                            "商業使用需另行取得授權：hunterip0305@gmail.com",
        "title_default": "美國專利家族關聯樹 — root {root}",
        "sum_cases": "{n} 件、{e} 條關聯",
        "sum_status": "狀態：{parts}",
        "sum_scope": "scope：{scope}",
        "sum_sep": "、",
        "sum_join": " ｜ ",
        "sum_trunc": {"rate-limit": "⚠️ 不完整(429)", "time-budget": "⚠️ 不完整(時間)",
                      "depth-cap": "⚠️ 深度上限", "node-cap": "⚠️ 節點上限", "_default": "⚠️ 已達上限"},
        "btn_reset": "⟳ 重設", "btn_dark": "🌙 深色", "btn_light": "☀ 淺色",
        "seg_gen": "世代排列", "seg_year": "年度排列",
        "ck_bar": "申請→領證 bar", "ck_flag": "copendency 紅旗",
        "count_suffix": "件顯示中",
        "grp_lineal": "直系", "tgl_lineal": "只看直系（隱藏旁系）",
        "grp_status": "狀態", "grp_rel": "關係", "grp_applicant": "申請人",
        "grp_down": "往下代數", "all_word": "全部", "gen_suffix": "代",
        "tt_status": "狀態：", "tt_filed": "申請 ", "tt_granted": "領證 ",
        "tt_lineage": "直系：",
        "lineage": {"root": "查詢起點", "ancestor": "祖先(優先權鏈)",
                    "descendant": "子孫", "collateral": "旁系"},
        "tt_boundary": "（邊界節點：未展開）",
        "tt_omitted": "另有 {n} 件關聯案未展開",
        "lbl_undated": "未定", "lbl_unexp": "⋯ 未展開", "lbl_notgranted": "— 未領證 —",
        "disc_flag": "⚠️ 紅旗 = 子案申請日晚於母案 pendency 結束日（領證/放棄）"
                     "→ 可能 §120 copendency 斷鏈，須逐案查證。",
        "disc_legal": "本圖為「已記載」之 US continuity 關係，非經完善之法律利益鏈"
                      "（cf. Natural Alternatives v. Iancu, 904 F.3d 1375）；僅供參考，非法律意見。",
        "foot_flag": "<span class=\"flag-k\">紅旗（copendency 警訊）</span>：子案的<b>申請日</b>晚於其"
                     "（可見）母案的 <b>pendency 結束日</b>（領證或放棄日）→ 該延續案可能在母案已非 pending "
                     "之後才提出，恐不符 35 U.S.C. §120 <b>copendency</b> 要件而喪失優先權利益。為啟發式提示，須逐案查證。",
        "foot_ops": "<b>操作</b>：點色塊/標籤即時過濾；「只看直系」隱藏旁系；「年度排列」以申請日為 Y 軸"
                    "（年份帶＋斑馬條）；hover 看完整詳情；下載即當前視圖（含說明、匯出固定淺色，適合報告）。",
        "foot_disc": "<b>免責</b>：本圖顯示為「<b>已記載</b>」之 US continuity（母子）關係，<b>非</b>經完善之"
                     "法律利益鏈；specific reference 全鏈完整與 copendency 斷鏈風險仍須逐案核對"
                     "（cf. <i>Natural Alternatives International v. Iancu</i>, 904 F.3d 1375 (Fed. Cir. 2018)）。"
                     "不含逐請求項 EFD 與巴黎公約外國優先權。僅供參考，<b>不構成法律意見</b>。"
                     "本工具為非官方工具，與 USPTO 無隸屬關係亦未經其背書。",
    },
}


def copyright_str(lang: str = "en") -> str:
    return f"© {COPYRIGHT_YEAR} {COPYRIGHT_HOLDER} · {STR_HTML[lang]['copyright_notice']}"


def minify_js(js: str) -> str:
    """壓縮嵌入的 JS 以降低可讀性（行為不變）。優先用 esbuild（真壓縮/改名區域變數），
    找不到就用零依賴的安全備援（去註解 + 去縮排）。"""
    import shutil
    import subprocess
    for eb in [os.environ.get("PATENT_ESBUILD"),
               shutil.which("esbuild")]:
        if eb and os.path.exists(eb):
            try:
                r = subprocess.run([eb, "--minify", "--loader=js"], input=js.encode("utf-8"),
                                   capture_output=True, check=True)
                out = r.stdout.decode("utf-8").strip()
                if out:
                    return out
            except Exception:
                pass
    # 安全備援：只丟掉整行註解與縮排（不動行內字串/正則）
    return "\n".join(t for t in (ln.strip() for ln in js.split("\n")) if t and not t.startswith("//"))

STATUS_STYLE = {
    "granted":     ("#e6f4ea", "#137333", "#0b3d1f"),
    "pending":     ("#ffffff", "#9aa0a6", "#3c4043"),
    "abandoned":   ("#9aa0a6", "#70757c", "#ffffff"),
    "provisional": ("#fff4e5", "#c26401", "#7a3d00"),
    "unknown":     ("#eef0f2", "#c0c4c9", "#6a6f76"),
}
_DARK = {
    "granted": ("#123522", "#3ea56a", "#c8ecd6"),
    "pending": ("#2a2d31", "#8a9096", "#e3e6ea"),
    "abandoned": ("#3b4048", "#565c64", "#e2e5ea"),
    "provisional": ("#3a2a12", "#d98a2b", "#f2d3a8"),
    "unknown": ("#22262c", "#3a4048", "#aeb4bc"),
}


def xml_esc(s) -> str:
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def svg_style() -> str:
    """Self-contained LIGHT theme inside the <svg> so downloads carry their colours."""
    out = [
        ".edge{stroke:#8a9096;stroke-width:1.4;fill:none;}",
        ".elabel{font-size:9.5px;fill:#5f6368;}",
        ".grid{stroke:#d5dae0;stroke-width:1;stroke-dasharray:4 4;}",
        ".zebra{fill:#f1f4f7;}",
        ".ylabel{font-size:17px;fill:#374151;font-weight:800;}",
        ".disc{font-size:11px;fill:#6a7178;}",
        ".credit{font-size:11.5px;fill:#8a9096;font-weight:600;}",
        ".bar{stroke:#b7c3cf;stroke-width:5;stroke-linecap:round;opacity:.7;}",
        ".node rect{stroke-width:1.6;}.node.stub rect{stroke-dasharray:4 3;}",
        ".node.flag rect{stroke:#d23f31;stroke-width:3;}",
        ".node .l1{font-size:13px;font-weight:600;}",
        ".node.root .l1{font-size:14px;font-weight:700;}",
        ".node .l2{font-size:11px;}.node .l3{font-size:10px;}",
    ]
    for st, (fill, stroke, fg) in STATUS_STYLE.items():
        out.append(f".node.{st} rect{{fill:{fill};stroke:{stroke};}}")
        out.append(f".node.{st} text{{fill:{fg};}}")
    out.append(".node.root rect{stroke-width:3.4;stroke:#0b6b32;}")
    out.append(".node.flag rect{stroke:#d23f31;stroke-width:3;}")  # flag wins over status stroke
    return "".join(out)


def svg_dark_overrides() -> str:
    """On-screen dark theme (data-theme=dark). Export keeps light (svg_style)."""
    P = ':root[data-theme="dark"] #famsvg '
    out = [P + ".edge{stroke:#6b7075;}", P + ".elabel{fill:#9aa4ae;}",
           P + ".grid{stroke:#2b313a;}", P + ".zebra{fill:#161b22;}",
           P + ".ylabel{fill:#c7cdd4;}", P + ".disc{fill:#8a9199;}",
           P + ".credit{fill:#9aa1a9;}", P + ".bar{stroke:#454e57;}"]
    for st, (fill, stroke, fg) in _DARK.items():
        out.append(f"{P}.node.{st} rect{{fill:{fill};stroke:{stroke};}}")
        out.append(f"{P}.node.{st} text{{fill:{fg};}}")
    out.append(P + ".node.root rect{stroke:#4fd08a;}")
    out.append(P + ".node.flag rect{stroke:#ff6b5e;}")
    return "".join(out)


def build_data(data: dict) -> dict:
    layer, _cyclic = assign_layers(data.get("nodes", []), data.get("edges", []), data.get("root"))
    nodes = []
    for n in data.get("nodes", []):
        app = n.get("applicationNumberText")
        ap = (n.get("applicant") or "").strip()
        nodes.append({
            "id": app, "gen": int(layer.get(app, 0)), "st": n.get("status", "unknown"),
            "sx": n.get("statusText"), "lin": n.get("lineage"),
            "ap": ap, "apk": " ".join(ap.upper().split()) or "—",
            "kind": n.get("kind"), "pat": n.get("patentNumber"), "ti": n.get("inventionTitle"),
            "fd": n.get("filingDate"), "gd": n.get("grantDate"), "sd": n.get("statusDate"),
            "f": 1 if n.get("_fetched", True) else 0, "om": int(n.get("_omitted", 0) or 0),
        })
    idset = {n.get("applicationNumberText") for n in data.get("nodes", [])}
    edges = []
    for e in data.get("edges", []):
        if e.get("from") in idset and e.get("to") in idset:
            short, disp = normalize_rel(e.get("relationshipType") or e.get("rawTypeCode", ""))
            edges.append({"f": e["from"], "t": e["to"], "r": short, "d": disp})
    return {"root": data.get("root"), "scope": data.get("scope", "full"),
            "truncated": bool(data.get("truncated")), "reason": data.get("truncationReason"),
            "nodes": nodes, "edges": edges}


def summary_line(d: dict, lang: str = "en") -> str:
    s = STR_HTML[lang]
    st = defaultdict(int)
    for n in d["nodes"]:
        st[n["st"]] += 1
    parts = s["sum_sep"].join(f"{s['status'].get(k, k)} {v}" for k, v in sorted(st.items()))
    bits = [
        s["sum_cases"].format(n=len(d["nodes"]), e=len(d["edges"])),
        s["sum_status"].format(parts=parts),
        s["sum_scope"].format(scope=d["scope"]),
    ]
    if d.get("truncated"):
        bits.append(s["sum_trunc"].get(d.get("reason"), s["sum_trunc"]["_default"]))
    return s["sum_join"].join(bits)


# ── 靜態 SVG（--svg-only 預覽用；世代排列）──────────────────────────
def _static_layout(nodes, edges, root):
    layer, _ = assign_layers(nodes, edges, root)
    by_app = {n["applicationNumberText"]: n for n in nodes}
    groups = defaultdict(list)
    for app in by_app:
        groups[layer[app]].append(app)
    for L in groups:
        groups[L].sort(key=lambda a: (by_app[a].get("filingDate") or "9999", a))
    max_cols = max((len(v) for v in groups.values()), default=1)
    total_w = MARGIN_X * 2 + max(max_cols, 1) * COL_GAP
    Ls = sorted(groups)
    total_h = MARGIN_Y * 2 + (len(Ls) - 1 if Ls else 0) * ROW_GAP + BOX_H
    pos = {}
    for row, L in enumerate(Ls):
        apps = groups[L]
        start = (total_w - len(apps) * COL_GAP) / 2 + COL_GAP / 2
        y = MARGIN_Y + row * ROW_GAP
        for i, app in enumerate(apps):
            pos[app] = (start + i * COL_GAP, y)
    return pos, total_w, total_h


def build_static_svg(data, title):
    nodes, edges, root = data.get("nodes", []), data.get("edges", []), data.get("root")
    by_app = {n["applicationNumberText"]: n for n in nodes}
    pos, W, H = _static_layout(nodes, edges, root)
    out = [
        f'<svg id="famsvg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" role="img" aria-label="{xml_esc(title)}">',
        f"<style>{svg_style()}</style>",
        '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#8a9096"/></marker></defs>',
        '<g id="viewport">',
    ]
    for e in edges:
        f, t = e.get("from"), e.get("to")
        if f in pos and t in pos:
            (fx, fy), (tx, ty) = pos[f], pos[t]
            out.append(f'<path class="edge" d="M{fx:.0f},{fy+BOX_H:.0f} L{tx:.0f},{ty:.0f}" marker-end="url(#ah)"/>')
    for app, (cx, ty) in pos.items():
        n = by_app[app]
        st = n.get("status") if n.get("status") in STATUS_STYLE else "unknown"
        cls = f"node {st}" + (" root" if app == root else "") + ("" if n.get("_fetched", True) else " stub")
        out.append(f'<g class="{cls}"><rect x="{cx-BOX_W/2:.0f}" y="{ty:.0f}" width="{BOX_W}" height="{BOX_H}" rx="9"/>'
                   f'<text class="l1" x="{cx:.0f}" y="{ty+24:.0f}" text-anchor="middle">{xml_esc(app)}</text></g>')
    out.append("</g></svg>")
    return "\n".join(out)


CSS = """
:root{--bg:#ffffff;--fg:#1f2328;--muted:#5f6368;--panel:#f6f8fa;--border:#d0d7de;--chip:#eef1f4;}
:root[data-theme="dark"]{--bg:#0d1117;--fg:#e6edf3;--muted:#9aa4ae;--panel:#161b22;--border:#30363d;--chip:#21262d;}
*{box-sizing:border-box;}
body{margin:0;background:var(--bg);color:var(--fg);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;}
.wrap{padding:12px 14px;}
h1{font-size:15px;margin:0 0 3px;}
.sum{font-size:12px;color:var(--muted);margin:0 0 8px;}
.bar-row{display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center;margin-bottom:8px;}
button{font:inherit;font-size:12px;padding:5px 10px;border:1px solid var(--border);background:var(--panel);color:var(--fg);border-radius:7px;cursor:pointer;}
button:hover{border-color:var(--muted);}
button.seg{border-radius:0;}
button.seg.first{border-radius:7px 0 0 7px;}
button.seg.last{border-radius:0 7px 7px 0;border-left:none;}
button.seg.on{background:var(--fg);color:var(--bg);}
label.ck{display:inline-flex;align-items:center;gap:4px;font-size:12px;color:var(--fg);cursor:pointer;}
.ctrls{display:flex;flex-wrap:wrap;gap:5px 14px;align-items:center;font-size:11.5px;color:var(--muted);margin-bottom:8px;}
.grp{display:flex;flex-wrap:wrap;gap:4px;align-items:center;}
.grp>b{font-weight:600;color:var(--fg);margin-right:2px;}
.chip{display:inline-flex;align-items:center;gap:5px;padding:2px 8px;border:1px solid var(--border);border-radius:20px;background:var(--chip);cursor:pointer;user-select:none;color:var(--fg);}
.chip.off{opacity:.4;text-decoration:line-through;}
.chip .sw{width:11px;height:11px;border-radius:3px;border:1px solid;}
.toggle{display:inline-flex;align-items:center;gap:5px;cursor:pointer;color:var(--fg);}
input[type=range]{vertical-align:middle;}
.stage{border:1px solid var(--border);border-radius:10px;overflow:hidden;background:var(--panel);height:70vh;min-height:420px;touch-action:none;}
#famsvg{display:block;width:100%;height:100%;cursor:grab;}
#famsvg.grabbing{cursor:grabbing;}
.foot{font-size:11.5px;color:var(--muted);margin-top:8px;line-height:1.55;border-top:1px solid var(--border);padding-top:7px;}
.foot p{margin:3px 0;}
.foot b{color:var(--fg);}
.foot .flag-k{color:#d23f31;font-weight:700;}
""".strip()


JS_APP = r"""
(function(){
  var D = window.__DATA__, SVGSTYLE = window.__SVGSTYLE__, T = window.__I18N__;
  var BOX_W=168, BOX_H=60, COL=196, ROW=140, MX=48, MY=72, YBAND=120, DISCH=52;
  var STLBL=T.status;
  var SW={granted:"#137333",pending:"#9aa0a6",abandoned:"#70757c",provisional:"#c26401",unknown:"#c0c4c9"};
  var byId={}; D.nodes.forEach(function(n){byId[n.id]=n;});
  var rootGen=(byId[D.root]||{gen:0}).gen;
  var STATUSES=["granted","pending","abandoned","provisional","unknown"].filter(function(s){return D.nodes.some(function(n){return n.st===s;});});
  var RELS=(function(){var s={};D.edges.forEach(function(e){s[e.r]=1;});return Object.keys(s);})();
  var ASG=(function(){var m={};D.nodes.forEach(function(n){if(!m[n.apk])m[n.apk]=n.ap||n.apk;});return m;})();
  var ASGKEYS=Object.keys(ASG);
  var maxDown=Math.max(0,Math.max.apply(null,D.nodes.map(function(n){return n.gen-rootGen;}).concat([0])));
  var hasCollateral=D.nodes.some(function(n){return n.lin==="collateral";});
  var S={lineal:false,status:new Set(STATUSES),rel:new Set(RELS),asg:new Set(ASGKEYS),down:maxDown,mode:"gen",bar:false,flag:false};

  function fmtApp(a){a=String(a);if(/^\d{8}$/.test(a))return a.slice(0,2)+"/"+a.slice(2,5)+","+a.slice(5);return a;}
  function esc(s){return(s==null?"":String(s)).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
  function relDisp(r){return {CON:"Continuation",CIP:"CIP",DIV:"Division",PRO:"provisional","371":"371",REX:"Reexam",REISSUE:"Reissue"}[r]||r;}
  function fy(d){ if(!d) return null; var m=String(d).match(/^(\d{4})-(\d{2})-(\d{2})/); if(m) return +m[1]+(+m[2]-1)/12+(+m[3]-1)/365; var y=String(d).match(/^(\d{4})/); return y?+y[1]:null; }
  function pendEnd(n){ return n.gd || (n.st==="abandoned"? n.sd : null) || null; }

  function nodePass(n){
    if(!S.status.has(n.st)) return false;
    if(!S.asg.has(n.apk)) return false;
    if(S.lineal && n.lin==="collateral") return false;
    if((n.gen-rootGen) > S.down) return false;
    return true;
  }
  function computeView(){
    var vis={}; D.nodes.forEach(function(n){ if(nodePass(n)) vis[n.id]=1; }); vis[D.root]=1;
    var ve=D.edges.filter(function(e){ return vis[e.f]&&vis[e.t]&&S.rel.has(e.r); });
    if(S.rel.size<RELS.length){
      var adj={}; ve.forEach(function(e){ (adj[e.f]=adj[e.f]||[]).push(e.t); (adj[e.t]=adj[e.t]||[]).push(e.f); });
      var reach={},q=[D.root]; reach[D.root]=1;
      while(q.length){ var x=q.shift(); (adj[x]||[]).forEach(function(y){ if(!reach[y]){reach[y]=1;q.push(y);} }); }
      Object.keys(vis).forEach(function(id){ if(!reach[id]&&id!==D.root) delete vis[id]; });
      ve=ve.filter(function(e){ return vis[e.f]&&vis[e.t]; });
    }
    return {vis:vis, ve:ve};
  }

  function layoutGen(vis, ve){
    var ids=D.nodes.filter(function(n){return vis[n.id];}).map(function(n){return n.id;});
    var rows={}; ids.forEach(function(id){ var g=byId[id].gen; (rows[g]=rows[g]||[]).push(id); });
    var gens=Object.keys(rows).map(Number).sort(function(a,b){return a-b;});
    gens.forEach(function(g){ rows[g].sort(function(a,b){ return (byId[a].fd||"9999").localeCompare(byId[b].fd||"9999")||a.localeCompare(b); }); });
    var adj={}; ve.forEach(function(e){ (adj[e.f]=adj[e.f]||[]).push(e.t); (adj[e.t]=adj[e.t]||[]).push(e.f); });
    for(var p=0;p<4;p++){ var idx={}; gens.forEach(function(g){ rows[g].forEach(function(id,i){ idx[id]=i; }); });
      gens.forEach(function(g){ rows[g].sort(function(a,b){
        function bc(x){ var ns=(adj[x]||[]).filter(function(y){return vis[y]&&byId[y].gen!==g&&idx[y]!=null;}).map(function(y){return idx[y];}); return ns.length?ns.reduce(function(s,v){return s+v;},0)/ns.length:idx[x]; }
        return bc(a)-bc(b)||(byId[a].fd||"9999").localeCompare(byId[b].fd||"9999"); }); }); }
    var maxCols=Math.max.apply(null,gens.map(function(g){return rows[g].length;}).concat([1]));
    var W=MX*2+Math.max(maxCols,1)*COL, H=MY*2+(gens.length?(gens.length-1)*ROW:0)+BOX_H+DISCH, pos={};
    gens.forEach(function(g,row){ var apps=rows[g],start=(W-apps.length*COL)/2+COL/2,y=MY+row*ROW; apps.forEach(function(id,i){ pos[id]=[start+i*COL,y]; }); });
    return {pos:pos,W:W,H:H,ve:ve,vis:vis,year:false};
  }

  function layoutYear(vis, ve){
    var ids=D.nodes.filter(function(n){return vis[n.id];}).map(function(n){return n.id;});
    var dated=ids.filter(function(id){return fy(byId[id].fd)!=null;});
    var undated=ids.filter(function(id){return fy(byId[id].fd)==null;});
    var minY=9999,maxY=0; dated.forEach(function(id){ var y=Math.floor(fy(byId[id].fd)); if(y<minY)minY=y; if(y>maxY)maxY=y; });
    if(!dated.length){minY=maxY=2000;}
    var band={}; dated.forEach(function(id){ var y=Math.floor(fy(byId[id].fd)); (band[y]=band[y]||[]).push(id); });
    Object.keys(band).forEach(function(y){ band[y].sort(function(a,b){ return (byId[a].fd||"").localeCompare(byId[b].fd||"")||a.localeCompare(b); }); });
    var maxCols=Math.max.apply(null,Object.keys(band).map(function(y){return band[y].length;}).concat([undated.length,1]));
    var W=MX*2+Math.max(maxCols,1)*COL;
    function yTop(y){ return MY+(y-minY)*YBAND; }
    var pos={};
    Object.keys(band).forEach(function(y){ var apps=band[y],start=(W-apps.length*COL)/2+COL/2;
      apps.forEach(function(id,i){ var f=fy(byId[id].fd),sub=f-Math.floor(f); pos[id]=[start+i*COL, yTop(+y)+sub*(YBAND-BOX_H)]; }); });
    var nY=maxY-minY+1, undY = undated.length? (MY+nY*YBAND+24) : null;
    if(undated.length){ var us=(W-undated.length*COL)/2+COL/2; undated.forEach(function(id,i){ pos[id]=[us+i*COL,undY]; }); }
    var H=(undated.length?undY+BOX_H:MY+nY*YBAND)+MY+DISCH;
    return {pos:pos,W:W,H:H,ve:ve,vis:vis,year:true,minY:minY,maxY:maxY,yTop:yTop,undY:undY};
  }

  function tooltip(n){
    var p=[fmtApp(n.id)]; if(n.ti)p.push(n.ti);
    var meta=[n.pat,n.ap,n.kind].filter(Boolean); if(meta.length)p.push(meta.join(" · "));
    if(n.sx)p.push(T.tt_status+n.sx);
    var d=[]; if(n.fd)d.push(T.tt_filed+n.fd); if(n.gd)d.push(T.tt_granted+n.gd); if(d.length)p.push(d.join(" · "));
    if(n.lin)p.push(T.tt_lineage+T.lineage[n.lin]);
    if(!n.f)p.push(T.tt_boundary);
    if(n.om)p.push(T.tt_omitted.replace("{n}",n.om));
    return p.join("\n");
  }

  var svg=document.getElementById("famsvg"), vp;
  function draw(){
    var v=computeView(), L=(S.mode==="year"?layoutYear:layoutGen)(v.vis,v.ve);
    var s='<style>'+SVGSTYLE+'</style>'+
      '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#8a9096"/></marker></defs><g id="viewport">';
    if(L.year){ for(var y=L.minY;y<=L.maxY;y++){ var gy=L.yTop(y);
        if((y-L.minY)%2===1) s+='<rect class="zebra" x="0" y="'+gy.toFixed(0)+'" width="'+L.W+'" height="'+YBAND+'"/>';
        s+='<line class="grid" x1="0" y1="'+gy.toFixed(0)+'" x2="'+L.W+'" y2="'+gy.toFixed(0)+'"/>'+
           '<text class="ylabel" x="12" y="'+(gy+YBAND/2+6).toFixed(0)+'">'+y+'</text>'; }
      if(L.undY!=null) s+='<text class="ylabel" x="12" y="'+(L.undY+34).toFixed(0)+'">'+esc(T.lbl_undated)+'</text>'; }
    // pendency (filing->grant) bar (year mode)
    if(L.year && S.bar){ Object.keys(L.pos).forEach(function(id){ var n=byId[id],f=fy(n.fd),g=fy(n.gd);
      if(f!=null&&g!=null&&g>f){ var x=L.pos[id][0], y1=L.pos[id][1]+BOX_H, len=(g-f)*YBAND;
        s+='<line class="bar" x1="'+x.toFixed(0)+'" y1="'+y1.toFixed(0)+'" x2="'+x.toFixed(0)+'" y2="'+(y1+len).toFixed(0)+'"/>'; } }); }
    // copendency red flags
    var flag={};
    if(S.flag){ L.ve.forEach(function(e){ var pn=byId[e.f],cn=byId[e.t],pe=pendEnd(pn); if(pe&&cn.fd&&cn.fd>pe) flag[e.t]=1; }); }
    var showLabels=L.ve.length<=40;
    L.ve.forEach(function(e){ var a=L.pos[e.f],b=L.pos[e.t]; if(!a||!b)return;
      s+='<path class="edge" d="M'+a[0].toFixed(0)+','+(a[1]+BOX_H).toFixed(0)+' L'+b[0].toFixed(0)+','+b[1].toFixed(0)+'" marker-end="url(#ah)"/>';
      if(showLabels){ s+='<text class="elabel" x="'+((a[0]+b[0])/2).toFixed(0)+'" y="'+((a[1]+BOX_H+b[1])/2).toFixed(0)+'" text-anchor="middle">'+esc(relDisp(e.r))+'</text>'; } });
    Object.keys(L.pos).forEach(function(id){ var n=byId[id],p=L.pos[id],cx=p[0],ty=p[1];
      var st=STLBL[n.st]?n.st:"unknown";
      var cls="node "+st+(id===D.root?" root":"")+(n.f?"":" stub")+(flag[id]?" flag":"");
      var head=(id===D.root?"★ ":"")+fmtApp(id);
      var l2=!n.f?T.lbl_unexp:(n.pat?n.pat:(st==="provisional"?"PROVISIONAL":T.lbl_notgranted));
      var bits=[STLBL[st]]; if(n.fd)bits.push(n.fd); if(n.om)bits.push("+"+n.om+"⋯");
      s+='<g class="'+cls+'"><title>'+esc(tooltip(n))+'</title>'+
        '<rect x="'+(cx-BOX_W/2).toFixed(0)+'" y="'+ty.toFixed(0)+'" width="'+BOX_W+'" height="'+BOX_H+'" rx="9"/>'+
        '<text class="l1" x="'+cx.toFixed(0)+'" y="'+(ty+21).toFixed(0)+'" text-anchor="middle">'+esc(head)+'</text>'+
        '<text class="l2" x="'+cx.toFixed(0)+'" y="'+(ty+38).toFixed(0)+'" text-anchor="middle">'+esc(l2)+'</text>'+
        '<text class="l3" x="'+cx.toFixed(0)+'" y="'+(ty+53).toFixed(0)+'" text-anchor="middle">'+esc(bits.join(" · "))+'</text></g>'; });
    // copyright: centred just below the lowest node (a subtle credit under the tree)
    if(window.__COPYRIGHT__){ var maxYb=0; Object.keys(L.pos).forEach(function(id){ var b=L.pos[id][1]+BOX_H; if(b>maxYb) maxYb=b; });
      s+='<text class="credit" x="'+(L.W/2).toFixed(0)+'" y="'+(maxYb+26).toFixed(0)+'" text-anchor="middle">'+esc(window.__COPYRIGHT__)+'</text>'; }
    // in-SVG disclaimer at the very bottom (so downloaded PNG/SVG carries it into reports)
    s+='<text class="disc" x="14" y="'+(L.H-30).toFixed(0)+'">'+esc(T.disc_flag)+'</text>';
    s+='<text class="disc" x="14" y="'+(L.H-13).toFixed(0)+'">'+esc(T.disc_legal)+'</text>';
    s+='</g>';
    svg.innerHTML=s; vp=svg.querySelector("#viewport");
    document.getElementById("count").textContent=Object.keys(L.pos).length+" "+T.count_suffix;
    fit(L.W,L.H);
  }

  var k=1,tx=0,ty=0,curW=1,curH=1;
  function apply(){ if(vp) vp.setAttribute("transform","translate("+tx+","+ty+") scale("+k+")"); }
  function fit(W,H){ curW=W;curH=H; var r=svg.getBoundingClientRect(); k=Math.min(r.width/W,r.height/H,1)*0.96; tx=(r.width-W*k)/2; ty=(r.height-H*k)/2; apply(); }
  svg.addEventListener("wheel",function(e){ e.preventDefault(); var r=svg.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top; var f=Math.exp(-e.deltaY*0.0015),nk=Math.min(Math.max(k*f,0.1),6); tx=mx-(mx-tx)*(nk/k); ty=my-(my-ty)*(nk/k); k=nk; apply(); },{passive:false});
  var drag=false,px,py;
  svg.addEventListener("pointerdown",function(e){ drag=true;px=e.clientX;py=e.clientY; svg.classList.add("grabbing"); svg.setPointerCapture(e.pointerId); });
  svg.addEventListener("pointermove",function(e){ if(!drag)return; tx+=e.clientX-px; ty+=e.clientY-py; px=e.clientX; py=e.clientY; apply(); });
  svg.addEventListener("pointerup",function(){ drag=false; svg.classList.remove("grabbing"); });

  function serialize(){ var saved=vp?vp.getAttribute("transform"):null; if(vp)vp.removeAttribute("transform");
    svg.setAttribute("viewBox","0 0 "+curW+" "+curH); svg.setAttribute("width",curW); svg.setAttribute("height",curH);
    var s='<?xml version="1.0" encoding="UTF-8"?>\n'+new XMLSerializer().serializeToString(svg);
    svg.removeAttribute("viewBox"); svg.removeAttribute("width"); svg.removeAttribute("height");
    if(vp&&saved)vp.setAttribute("transform",saved); return s; }
  function dl(name,url){ var a=document.createElement("a"); a.href=url; a.download=name; document.body.appendChild(a); a.click(); a.remove(); }
  document.getElementById("svgbtn").onclick=function(){ dl("patent-family.svg",URL.createObjectURL(new Blob([serialize()],{type:"image/svg+xml"}))); };
  document.getElementById("pngbtn").onclick=function(){ var s=serialize(),img=new Image();
    img.onload=function(){ var sc=2,c=document.createElement("canvas"); c.width=curW*sc; c.height=curH*sc; var ctx=c.getContext("2d");
      ctx.fillStyle="#ffffff"; ctx.fillRect(0,0,c.width,c.height); ctx.setTransform(sc,0,0,sc,0,0); ctx.drawImage(img,0,0);
      c.toBlob(function(b){ dl("patent-family.png",URL.createObjectURL(b)); },"image/png"); };
    img.src="data:image/svg+xml;base64,"+btoa(unescape(encodeURIComponent(s))); };
  document.getElementById("reset").onclick=function(){ fit(curW,curH); };

  // theme toggle (button label shows the action = the theme it will switch TO)
  var themeBtn=document.getElementById("theme");
  function setThemeLabel(){ themeBtn.textContent=document.documentElement.getAttribute("data-theme")==="dark"?T.btn_light:T.btn_dark; }
  setThemeLabel();
  themeBtn.onclick=function(){ var cur=document.documentElement.getAttribute("data-theme")==="dark"?"light":"dark"; document.documentElement.setAttribute("data-theme",cur); setThemeLabel(); };
  // layout mode
  var segGen=document.getElementById("mgen"), segYear=document.getElementById("myear");
  segGen.onclick=function(){ S.mode="gen"; segGen.classList.add("on"); segYear.classList.remove("on"); yearOpts.style.display="none"; draw(); };
  segYear.onclick=function(){ S.mode="year"; segYear.classList.add("on"); segGen.classList.remove("on"); yearOpts.style.display=""; draw(); };
  var yearOpts=document.getElementById("yearopts");
  document.getElementById("barck").onchange=function(e){ S.bar=e.target.checked; draw(); };
  document.getElementById("flagck").onchange=function(e){ S.flag=e.target.checked; draw(); };

  // filter chips
  function chip(label,on,sw,onclick){ var c=document.createElement("span"); c.className="chip"+(on?"":" off");
    c.innerHTML=(sw?'<i class="sw" style="background:'+sw+';border-color:'+sw+'"></i>':'')+esc(label); c.onclick=function(){onclick(c);}; return c; }
  var ctr=document.getElementById("ctrls");
  function group(title){ var g=document.createElement("span"); g.className="grp"; g.innerHTML="<b>"+title+"</b>"; ctr.appendChild(g); return g; }
  if(hasCollateral){ var lg=group(T.grp_lineal); var lc=document.createElement("label"); lc.className="toggle";
    lc.innerHTML='<input type="checkbox"> '+esc(T.tgl_lineal); lc.querySelector("input").onchange=function(e){ S.lineal=e.target.checked; draw(); }; lg.appendChild(lc); }
  var sg=group(T.grp_status); STATUSES.forEach(function(st){ sg.appendChild(chip(STLBL[st],true,SW[st],function(c){ if(S.status.has(st)){S.status.delete(st);c.classList.add("off");}else{S.status.add(st);c.classList.remove("off");} draw(); })); });
  if(RELS.length>1){ var rg=group(T.grp_rel); RELS.forEach(function(r){ rg.appendChild(chip(relDisp(r),true,null,function(c){ if(S.rel.has(r)){S.rel.delete(r);c.classList.add("off");}else{S.rel.add(r);c.classList.remove("off");} draw(); })); }); }
  if(ASGKEYS.length>1){ var ag=group(T.grp_applicant); ASGKEYS.forEach(function(kk){ var lbl=ASG[kk]; if(lbl.length>22)lbl=lbl.slice(0,21)+"…"; ag.appendChild(chip(lbl,true,null,function(c){ if(S.asg.has(kk)){S.asg.delete(kk);c.classList.add("off");}else{S.asg.add(kk);c.classList.remove("off");} draw(); })); }); }
  if(maxDown>1){ var dg=group(T.grp_down); var rng=document.createElement("input"); rng.type="range"; rng.min=1; rng.max=maxDown; rng.value=maxDown; var lab=document.createElement("span"); lab.textContent=T.all_word;
    rng.oninput=function(){ S.down=+rng.value; lab.textContent=(+rng.value>=maxDown?T.all_word:rng.value+" "+T.gen_suffix); draw(); }; dg.appendChild(rng); dg.appendChild(lab); }

  window.addEventListener("resize",function(){ fit(curW,curH); });
  window.__app__={computeView:computeView,layoutGen:layoutGen,layoutYear:layoutYear,S:S,root:D.root,byId:byId,nodes:D.nodes,pendEnd:pendEnd};
  draw();
})();
"""


def build_html(data: dict, title: str, minify: bool = False, lang: str = "en") -> str:
    s = STR_HTML[lang]
    d = build_data(data)
    js = minify_js(JS_APP) if minify else JS_APP
    copyright_line = copyright_str(lang)
    return (
        f"<!doctype html>\n<html lang=\"{s['htmllang']}\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{xml_esc(title)}</title>"
        "<script>document.documentElement.setAttribute('data-theme',"
        "matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');</script>"
        f"<style>{CSS}\n{svg_dark_overrides()}</style></head>"
        "<body><div class=\"wrap\">"
        f"<h1>{xml_esc(title)}</h1>"
        f"<p class=\"sum\">{xml_esc(summary_line(d, lang))}</p>"
        "<div class=\"bar-row\">"
        "<button id=\"pngbtn\">⬇ PNG</button><button id=\"svgbtn\">⬇ SVG</button>"
        f"<button id=\"reset\">{xml_esc(s['btn_reset'])}</button>"
        f"<button id=\"theme\">{xml_esc(s['btn_dark'])}</button>"
        "<span style=\"width:8px\"></span>"
        f"<button id=\"mgen\" class=\"seg first on\">{xml_esc(s['seg_gen'])}</button>"
        f"<button id=\"myear\" class=\"seg last\">{xml_esc(s['seg_year'])}</button>"
        "<span id=\"yearopts\" style=\"display:none\">"
        f"<label class=\"ck\"><input type=\"checkbox\" id=\"barck\"> {xml_esc(s['ck_bar'])}</label> "
        f"<label class=\"ck\"><input type=\"checkbox\" id=\"flagck\"> {xml_esc(s['ck_flag'])}</label></span>"
        "<span class=\"sum\" id=\"count\"></span></div>"
        "<div class=\"ctrls\" id=\"ctrls\"></div>"
        "<div class=\"stage\"><svg id=\"famsvg\" xmlns=\"http://www.w3.org/2000/svg\" "
        f"role=\"img\" aria-label=\"{xml_esc(title)}\"></svg></div>"
        "<div class=\"foot\">"
        f"<p>{s['foot_flag']}</p>"
        f"<p>{s['foot_ops']}</p>"
        f"<p>{s['foot_disc']}</p>"
        f"<p style=\"margin-top:5px;opacity:.85\">{xml_esc(copyright_line)}</p>"
        "</div>"
        "</div>"
        f"<script>window.__DATA__={json.dumps(d, ensure_ascii=False)};"
        f"window.__SVGSTYLE__={json.dumps(svg_style(), ensure_ascii=False)};"
        f"window.__I18N__={json.dumps(s, ensure_ascii=False)};"
        f"window.__COPYRIGHT__={json.dumps(copyright_line, ensure_ascii=False)};</script>"
        f"<script>{js}</script></body></html>"
    )


def main(argv):
    ap = argparse.ArgumentParser(description="family_raw.json → interactive HTML (filters / year-axis / theme / export)")
    ap.add_argument("input")
    ap.add_argument("-o", "--out", help="output HTML path (default stdout)")
    ap.add_argument("--title", default=None)
    ap.add_argument("--svg-only", action="store_true", help="print the static SVG only (preview)")
    ap.add_argument("--minify", action="store_true", help="minify the embedded JS (lower readability; behaviour unchanged)")
    ap.add_argument("--lang", default=lang_default(), choices=["en", "zh"],
                    help="UI language (default: en, or env PATENT_FAMILY_LANG)")
    args = ap.parse_args(argv)

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)
    title = args.title or STR_HTML[args.lang]["title_default"].format(root=data.get("root", "?"))

    from validate import validate_family_raw
    problems = validate_family_raw(data)
    if problems:
        print("⚠️ family_raw contract-validation warnings:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)

    if args.svg_only:
        print(build_static_svg(data, title))
        return 0
    html = build_html(data, title, minify=args.minify, lang=args.lang)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"wrote {args.out} ({len(html)} bytes)")
    else:
        print(html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
