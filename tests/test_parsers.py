"""解析与实体抽取：文件进来必须变成「有锚点的块」，否则后面全塌。"""

from __future__ import annotations

from medpal_core.assets import parsers
from medpal_core.assets.entity import Lexicon, default_lexicon


def test_parse_markdown_yields_blocks_and_anchors(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("# 标题\n\n上腹隐痛多于餐后加重。\n", encoding="utf-8")
    doc = parsers.parse(f)
    assert doc is not None
    assert len(doc.blocks) == 2
    assert any(b.kind == "heading" for b in doc.blocks)
    assert all("#" in a["anchor_id"] for a in doc.anchors)


def test_unknown_suffix_has_no_parser(tmp_path):
    f = tmp_path / "x.xyz"
    f.write_text("x", encoding="utf-8")
    assert parsers.pick(f) is None
    assert parsers.parse(f) is None


def test_lexicon_longest_match_and_synonym(conn_unused=None):
    lex = Lexicon(terms=["胃镜", "胃食管反流病", "上腹痛"], synonyms={"上腹痛": "上腹隐痛"})
    assert lex.extract(["有胃食管反流病，复查胃镜"]) == ["胃食管反流病", "胃镜"]
    assert lex.extract(["上腹痛三个月"]) == ["上腹隐痛"]


def test_default_lexicon_loads_repo_data():
    lex = default_lexicon()
    assert "消化性溃疡" in lex.terms
    assert lex.category("胃镜") == "exam"
