#!/usr/bin/env python3
"""Layer 3 回歸測試（stdlib unittest，零依賴）。

    python -m unittest discover -s tests    # 或
    python tests/test_render.py
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "build"))
import render_mermaid as R  # noqa: E402

FIX = os.path.join(ROOT, "fixtures")


def load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


class NormalizeRel(unittest.TestCase):
    def test_cip_before_con(self):
        # "Continuation in part" 含 CON，但必須先判成 CIP
        self.assertEqual(R.normalize_rel("Continuation in part")[0], "CIP")

    def test_known_codes(self):
        self.assertEqual(R.normalize_rel("Continuation")[0], "CON")
        self.assertEqual(R.normalize_rel("Division")[0], "DIV")
        self.assertEqual(R.normalize_rel("Provisional application")[0], "PRO")
        self.assertEqual(R.normalize_rel("371 national stage")[0], "371")

    def test_unknown_preserved(self):
        short, disp = R.normalize_rel("Weird Custom Type")
        self.assertEqual(short, "UNKNOWN")
        self.assertEqual(disp, "Weird Custom Type")  # 不靜默吞掉


class MermaidSafety(unittest.TestCase):
    def test_node_id_unique_and_legal(self):
        used = {}
        a = R.node_id("15/643,719", used)
        b = R.node_id("15/643,719", used)  # 同號回同 id
        self.assertEqual(a, b)
        self.assertNotIn("/", a)
        self.assertNotIn(",", a)

    def test_label_escapes_quote_and_hash(self):
        node = {"applicationNumberText": "X", "status": "pending", "_fetched": True,
                "inventionTitle": 'has "quote" and #hash'}
        label = R.node_label(node, is_root=False, max_title=99)
        self.assertNotIn('"has', label)         # 原始引號不得外洩
        self.assertIn("&quot;", label)
        self.assertIn("#35;", label)


class RenderSimpleChain(unittest.TestCase):
    def setUp(self):
        self.data = load("simple_chain.json")
        self.out = R.render(self.data, direction="LR")

    def test_direction_and_nodes(self):
        self.assertTrue(self.out.startswith("flowchart LR"))
        for app in ("12/300,010", "12/300,020", "12/300,030"):
            self.assertIn(R.node_id(app, {}), self.out)

    def test_edges_labeled_continuation(self):
        self.assertEqual(self.out.count("-->|Continuation|"), 2)

    def test_root_marked(self):
        self.assertIn("★", self.out)
        self.assertIn("stroke-width:4px", self.out)


class RenderCipFork(unittest.TestCase):
    def setUp(self):
        self.data = load("cip_fork.json")
        self.out = R.render(self.data, direction="TD")
        self.summary = R.summarize(self.data)

    def test_all_status_classes_present(self):
        for st in ("granted", "pending", "abandoned", "provisional", "unknown"):
            self.assertIn(f"classDef {st} ", self.out)

    def test_unexpanded_node_rendered(self):
        self.assertIn("not expanded", self.out)  # English is the default UI language

    def test_overlay_badge(self):
        self.assertIn("INPADOC", self.out)
        self.assertIn("EP9000001A1", self.out)

    def test_summary_detects_cip_and_merge(self):
        self.assertIn("CIP break points", self.summary)
        self.assertIn("DAG merges", self.summary)
        self.assertIn("Un-expanded boundary nodes", self.summary)


class I18n(unittest.TestCase):
    """The UI language switch (en default / zh) applies to both renderers."""
    def setUp(self):
        self.data = load("cip_fork.json")

    def test_mermaid_zh_labels(self):
        out = R.render(self.data, direction="TD", lang="zh")
        summ = R.summarize(self.data, lang="zh")
        self.assertIn("未領證", out)
        self.assertIn("家族摘要", summ)
        self.assertIn("CIP 斷點", summ)

    def test_mermaid_en_is_default(self):
        # no lang arg → English
        self.assertIn("not granted", R.render(self.data, direction="TD"))
        self.assertIn("Family summary", R.summarize(self.data))

    def test_html_lang_attr_and_strings(self):
        import render_html as H
        en = H.build_html(self.data, "t", lang="en")
        zh = H.build_html(self.data, "t", lang="zh")
        self.assertIn('lang="en"', en)
        self.assertIn("By generation", en)
        self.assertIn("not legal advice", en)
        self.assertIn('lang="zh-Hant"', zh)
        self.assertIn("世代排列", zh)
        self.assertIn("不構成法律意見", zh)


class FixtureSchemaLite(unittest.TestCase):
    """輕量契約檢查：fixture 必須符合 family_raw.schema 的必填欄位。"""
    REQUIRED_NODE = {"applicationNumberText", "status", "_fetched"}
    REQUIRED_EDGE = {"from", "to", "relationshipType"}
    VALID_STATUS = {"granted", "pending", "abandoned", "provisional", "unknown"}

    def _check(self, name):
        d = load(name)
        self.assertIn("root", d)
        apps = {n["applicationNumberText"] for n in d["nodes"]}
        for n in d["nodes"]:
            self.assertTrue(self.REQUIRED_NODE <= set(n), f"{name}: node missing required")
            self.assertIn(n["status"], self.VALID_STATUS)
        for e in d["edges"]:
            self.assertTrue(self.REQUIRED_EDGE <= set(e), f"{name}: edge missing required")
            # 邊兩端都必須有對應節點（無懸空邊）
            self.assertIn(e["from"], apps, f"{name}: dangling edge.from {e['from']}")
            self.assertIn(e["to"], apps, f"{name}: dangling edge.to {e['to']}")

    def test_simple_chain(self):
        self._check("simple_chain.json")

    def test_cip_fork(self):
        self._check("cip_fork.json")


class Validator(unittest.TestCase):
    def setUp(self):
        import validate as V
        self.V = V

    def test_fixtures_are_valid(self):
        for name in ("simple_chain.json", "cip_fork.json"):
            self.assertEqual(self.V.validate_family_raw(load(name)), [], name)

    def test_catches_dangling_edge_and_bad_status(self):
        bad = {
            "root": "A",
            "nodes": [
                {"applicationNumberText": "A", "status": "granted", "_fetched": True},
                {"applicationNumberText": "B", "status": "bogus", "_fetched": True},
            ],
            "edges": [{"from": "A", "to": "Z", "relationshipType": "CON"}],
        }
        errs = self.V.validate_family_raw(bad)
        joined = " ".join(errs)
        self.assertIn("bogus", joined)          # bad status enum
        self.assertIn("references no node", joined)  # dangling edge -> Z

    def test_catches_duplicate_and_missing_root(self):
        bad = {
            "root": "X",
            "nodes": [
                {"applicationNumberText": "A", "status": "granted", "_fetched": True},
                {"applicationNumberText": "A", "status": "granted", "_fetched": True},
            ],
            "edges": [],
        }
        errs = self.V.validate_family_raw(bad)
        joined = " ".join(errs)
        self.assertIn("duplicate", joined)
        self.assertIn("root 'X'", joined)


class HtmlLayering(unittest.TestCase):
    """render_html 的拓撲分層：每條邊必往下（child 世代 > parent），root 正規化為 0。"""
    def setUp(self):
        import render_html as H
        self.H = H

    def test_edges_point_downward_and_root_zero(self):
        data = load("cip_fork.json")
        layer, cyclic = self.H.assign_layers(data["nodes"], data["edges"], data["root"])
        self.assertFalse(cyclic)
        self.assertEqual(layer[data["root"]], 0)
        idset = {n["applicationNumberText"] for n in data["nodes"]}
        for e in data["edges"]:
            if e["from"] in idset and e["to"] in idset:
                self.assertLess(layer[e["from"]], layer[e["to"]],
                                f"edge {e['from']}→{e['to']} must go downward")

    def test_provisional_parent_above_root(self):
        # cip_fork: 61/100,010 是 root(12/300,020) 的 provisional 母案 → 世代須為負
        data = load("cip_fork.json")
        layer, _ = self.H.assign_layers(data["nodes"], data["edges"], data["root"])
        self.assertLess(layer["61/100,010"], 0)

    def test_build_html_self_contained(self):
        data = load("cip_fork.json")
        html = self.H.build_html(data, "t")
        self.assertIn("<svg", html)
        self.assertIn('id="pngbtn"', html)
        self.assertNotIn("http://", html.replace("http://www.w3.org", ""))  # 無外部資源（xmlns 除外）


class PhaseBDynamicHtml(unittest.TestCase):
    def setUp(self):
        import render_html as H
        self.H = H

    def test_build_data_annotates_gen_and_normalizes_applicant(self):
        data = {
            "root": "A", "scope": "full",
            "nodes": [
                {"applicationNumberText": "A", "status": "granted", "_fetched": True,
                 "applicant": "MASSACHUSETTS INSTITUTE OF  TECHNOLGY", "lineage": "root"},
                {"applicationNumberText": "B", "status": "pending", "_fetched": True,
                 "applicant": "Massachusetts Institute of Technology", "lineage": "descendant"},
            ],
            "edges": [{"from": "A", "to": "B", "relationshipType": "CON"}],
        }
        d = self.H.build_data(data)
        by = {n["id"]: n for n in d["nodes"]}
        self.assertEqual(by["A"]["gen"], 0, "root generation normalized to 0")
        self.assertEqual(by["B"]["gen"], 1, "child one generation down")
        self.assertEqual(by["A"]["lin"], "root")
        # applicant key normalizes case + collapses whitespace (but the two above differ by a typo,
        # so they stay distinct — the point is deterministic normalization)
        self.assertEqual(by["B"]["apk"], "MASSACHUSETTS INSTITUTE OF TECHNOLOGY")
        self.assertEqual(d["edges"][0]["r"], "CON")

    def test_build_html_embeds_data_and_controls(self):
        html = self.H.build_html(load("cip_fork.json"), "t")
        self.assertIn("window.__DATA__", html)
        self.assertIn("window.__SVGSTYLE__", html)
        self.assertIn('id="pngbtn"', html)
        self.assertIn("id=\"ctrls\"", html)
        self.assertIn("<svg", html)
        # self-contained: no external hosts (xmlns is the only http reference)
        self.assertNotIn("http://", html.replace("http://www.w3.org", ""))


if __name__ == "__main__":
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.join(ROOT, "build"))
    unittest.main(verbosity=2)
