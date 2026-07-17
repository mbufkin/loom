"""Crystallize print theme (HTML/CSS → WeasyPrint)."""

from pdf_theme.md_to_html import extract_h1, md_to_html
from pdf_theme.render import render_packet_pdf, year_at_a_glance_html

__all__ = [
    "extract_h1",
    "md_to_html",
    "render_packet_pdf",
    "year_at_a_glance_html",
]
