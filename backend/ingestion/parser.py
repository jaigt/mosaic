"""
Parses raw SEC filing HTML into structured elements using Unstructured.io (local, free).
Groups elements by SEC section (Item 1, Item 7: MD&A, etc.) based on headers.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

from unstructured.partition.html import partition_html
from unstructured.documents.elements import (
    Title, NarrativeText, Table, Element
)

logger = logging.getLogger(__name__)

# Regex to detect SEC form item headers (e.g., "Item 1A.", "ITEM 7.")
_SECTION_HEADER_RE = re.compile(
    r"^(item\s+\d+[a-z]?\.?\s*.{0,60})$",
    re.IGNORECASE,
)


@dataclass
class ParsedElement:
    element_type: str          # "text" | "table"
    content: str               # NarrativeText body or raw table HTML/Markdown
    section: str               # e.g., "Item 7: MD&A"
    raw_html: Optional[str] = None  # Original HTML for tables


@dataclass
class ParsedDocument:
    elements: list[ParsedElement] = field(default_factory=list)
    section_map: dict[str, list[ParsedElement]] = field(default_factory=dict)


def parse_filing_html(html_content: str) -> ParsedDocument:
    """
    Partition HTML into elements, track section headers, and return a
    ParsedDocument with elements grouped by SEC section.
    """
    logger.info("Partitioning HTML with Unstructured.io")
    raw_elements: list[Element] = partition_html(text=html_content)
    logger.info(f"Found {len(raw_elements)} raw elements")

    doc = ParsedDocument()
    current_section = "Preamble"

    for el in raw_elements:
        text = str(el).strip()
        if not text:
            continue

        # Detect section transitions from Title or bold-ish text
        if isinstance(el, Title) or _SECTION_HEADER_RE.match(text):
            current_section = _normalize_section_name(text)
            logger.debug(f"New section: {current_section}")
            continue

        if isinstance(el, Table):
            parsed = ParsedElement(
                element_type="table",
                content=text,          # Unstructured's text representation
                section=current_section,
                raw_html=getattr(el, "metadata", None) and el.metadata.text_as_html,
            )
        else:
            # NarrativeText, ListItem, etc. — treat as text
            parsed = ParsedElement(
                element_type="text",
                content=text,
                section=current_section,
            )

        doc.elements.append(parsed)
        doc.section_map.setdefault(current_section, []).append(parsed)

    logger.info(
        f"Parsed {len(doc.elements)} elements across {len(doc.section_map)} sections"
    )
    return doc


def _normalize_section_name(raw: str) -> str:
    """Clean up section header text for use as metadata."""
    # Collapse whitespace, title-case
    return re.sub(r"\s+", " ", raw).strip()
