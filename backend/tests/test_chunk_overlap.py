"""Tests for sliding-window overlap in _merge_text_elements.

A fact spanning a size-based chunk boundary must appear whole in at least one
chunk; section changes must remain hard breaks with no overlap bleed.
"""
from backend.ingestion.parser import ParsedElement
from backend.pipeline.ingest import (
    _TEXT_CHUNK_OVERLAP,
    _TEXT_CHUNK_TARGET,
    _merge_text_elements,
    _tail_overlap,
)


def _text(content: str, section: str = "Item 7") -> ParsedElement:
    return ParsedElement(element_type="text", content=content, section=section)


def test_size_split_carries_overlap():
    # First element fills the buffer past the target; second triggers a split.
    first = "alpha " * (_TEXT_CHUNK_TARGET // 6 + 10)
    second = "beta " * 50
    merged = _merge_text_elements([_text(first.strip()), _text(second.strip())])

    assert len(merged) == 2
    tail_of_first = merged[0].content[-50:]
    # The tail of chunk 1 must reappear at the start of chunk 2.
    assert tail_of_first in merged[1].content
    assert merged[1].content.startswith(_tail_overlap(merged[0].content)[:20])


def test_section_change_has_no_overlap():
    first = "alpha " * (_TEXT_CHUNK_TARGET // 6 + 10)
    merged = _merge_text_elements([
        _text(first.strip(), section="Item 7"),
        _text("risk factors text " * 20, section="Item 1A"),
    ])
    assert len(merged) == 2
    assert merged[1].section == "Item 1A"
    assert "alpha" not in merged[1].content


def test_small_elements_merge_without_overlap_artifacts():
    merged = _merge_text_elements([_text("one."), _text("two."), _text("three.")])
    assert len(merged) == 1
    assert merged[0].content == "one.\n\ntwo.\n\nthree."


def test_tail_overlap_bounds_and_word_boundary():
    text = "word " * 200
    tail = _tail_overlap(text.strip())
    assert len(tail) <= _TEXT_CHUNK_OVERLAP
    assert not tail.startswith(" ")
    assert tail.startswith("word")

    # Short text returned unchanged.
    assert _tail_overlap("short") == "short"
