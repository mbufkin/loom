"""Chunking and paragraph structure for documents that arrive without paragraphs.

Both failures here were found measuring the TEA Bluebonnet Algebra I teacher
edition, a 350,000-character PDF, before committing to a long run against it.

PDF text extraction produces single newlines and no blank lines at all. That
breaks two assumptions at once: paragraph-range citation, which is the only
reason excerpts in the ledger are verbatim, and the chunker's overlap, which
assumed paragraphs are small compared to a chunk.
"""

import statistics

import audit_lib
import layer0


# --- the chunker -----------------------------------------------------------


def test_a_document_with_no_blank_lines_still_chunks_to_the_budget():
    """The overlap runaway: chunks reached 3x the budget and billed 2.4x.

    The oversized-paragraph guard slices a blank-line-free document into pieces
    of chunk_size each. Carrying two of those forward as "overlap" started the
    next chunk at twice the budget before adding anything new, so sizes ran
    60K/120K/180K/180K/180K on a 300K document and the same text was sent to
    the model two or three times.
    """
    text = "x" * 300_000

    chunks = layer0.split_into_chunks(text, chunk_size=60_000)

    assert max(len(c) for c in chunks) <= 60_000, (
        f"chunk exceeded the budget: {[len(c) for c in chunks]}"
    )
    billed = sum(len(c) for c in chunks)
    assert billed <= len(text) * 1.1, (
        f"sent {billed / len(text):.1f}x the document to the model"
    )


def test_normal_prose_still_overlaps_across_the_boundary():
    """The overlap exists to stop an element being severed, and must survive.

    Capping it by size must not silently turn it off for the ordinary case it
    was built for.
    """
    paragraphs = [f"paragraph {i} " + "y" * 400 for i in range(40)]
    text = "\n\n".join(paragraphs)

    chunks = layer0.split_into_chunks(text, chunk_size=4_000)

    assert len(chunks) > 2, "test needs several chunks to have a boundary"
    # The tail of one chunk reappears at the head of the next.
    for earlier, later in zip(chunks, chunks[1:]):
        tail = earlier.split("\n\n")[-1]
        assert tail in later, "overlap was dropped at a chunk boundary"


def test_overlap_never_costs_more_than_its_share_of_a_chunk():
    """A paragraph too big to be useful context is not carried forward at all."""
    big = "z" * 50_000
    small = "w" * 500
    text = "\n\n".join([big, small, big, small])

    chunks = layer0.split_into_chunks(text, chunk_size=60_000)

    budget = 60_000 * layer0.OVERLAP_MAX_FRACTION
    for c in chunks:
        first = c.split("\n\n")[0]
        if len(first) > budget:
            # It may only appear as a chunk's own content, never as overlap.
            assert c.startswith(big) or c.startswith(small)
    assert max(len(c) for c in chunks) <= 60_000


def test_a_short_document_is_left_as_one_chunk():
    """Chunking only applies above the threshold; small documents are untouched."""
    text = "\n\n".join(f"para {i}" for i in range(5))

    assert layer0.split_into_chunks(text, chunk_size=60_000) == [text]


# --- paragraph structure ---------------------------------------------------


def test_pdf_text_with_no_blank_lines_gains_paragraphs():
    """Without this the whole document is one paragraph, so every citation in it
    resolves to the entire document and the ledger cannot say where anything
    came from."""
    lines = [f"This is line {i} of a teacher edition page." for i in range(400)]
    raw = "\n".join(lines)

    cleaned = audit_lib.clean_document_text(raw)
    _, paragraphs = layer0.number_paragraphs(cleaned)

    assert len(paragraphs) > 1, "document is still a single paragraph"
    assert statistics.median(len(p) for p in paragraphs) < 2_000


def test_reflow_keeps_every_character_in_order():
    """Excerpts are sliced out of this text, so it has to stay verbatim.

    Reflow is only allowed to promote existing line breaks to paragraph breaks.
    Comparing with whitespace collapsed is the same test excerpt_cited_in
    applies to a resolved excerpt.
    """
    raw = "\n".join(f"line {i} carries real content" for i in range(300))

    reflowed = audit_lib.reflow_paragraphs(raw)

    assert audit_lib.normalize_ws(reflowed) == audit_lib.normalize_ws(raw)


def test_a_document_that_already_has_paragraphs_is_untouched():
    """HTML and Markdown sources must come through byte for byte.

    The guard is what keeps every corpus already in the repo unaffected.
    """
    text = "\n\n".join(f"Block {i} of ordinary prose." for i in range(50))

    assert audit_lib.clean_document_text(text) == text
    assert not audit_lib.looks_unstructured(text)


def test_reflow_starts_a_new_paragraph_at_a_heading():
    """A cited range should line up with something a teacher recognises."""
    raw = (
        "Students compare rates of change across representations.\n"
        "They justify which representation is most useful.\n"
        "LESSON 3: Comparing Linear Functions\n"
        "Begin with the warm up on page 42.\n"
    )

    paragraphs = audit_lib.reflow_paragraphs(raw).split("\n\n")

    assert any(p.startswith("LESSON 3") for p in paragraphs), (
        f"heading did not begin a paragraph: {paragraphs}"
    )


def test_reflow_does_not_break_on_every_bullet():
    """The tuning decision, pinned because it is easy to undo by accident.

    Breaking on list markers took the median paragraph on the Bluebonnet module
    from 700 characters to 86, with 17% of paragraphs under 40 -- fragments too
    small to stand as evidence. It also multiplies Layer 0-B calls, which fire
    on any span wider than WIDE_SPAN_PARAGRAPHS, and a bulleted lesson crosses
    that on paragraph count while covering a single idea.
    """
    raw = "\n".join(
        ["Guided practice for this topic:"]
        + [f"- step {i} of the worked example" for i in range(10)]
    )

    paragraphs = audit_lib.reflow_paragraphs(raw).split("\n\n")

    assert len(paragraphs) == 1, f"bullets were split apart: {paragraphs}"


def test_the_threshold_treats_a_sparse_long_document_as_unstructured():
    """Two blank lines in 300,000 characters is not paragraph structure.

    This is the real shape of the Bluebonnet teacher edition after cleaning.
    """
    text = ("a" * 150_000) + "\n\n" + ("b" * 150_000)

    assert audit_lib.looks_unstructured(text)


def test_a_few_blank_lines_do_not_count_as_structure():
    """Counting breaks is the wrong question; their spacing is the right one.

    The Bluebonnet student edition course guide has seventeen blank lines in
    68,615 characters. That reads as structured if you only count breaks, but
    each paragraph is 3,800 characters -- far too coarse to cite, and exactly
    the case an earlier version of this check waved through.
    """
    # Each block is many short lines, which is what PDF text actually looks
    # like -- reflow can only split where a line break already exists.
    block = "\n".join("course guide line of text" for _ in range(150))
    text = "\n\n".join(block for _ in range(18))

    assert audit_lib.looks_unstructured(text)

    rebuilt = audit_lib.reflow_paragraphs(text)
    paragraphs = [p for p in rebuilt.split("\n\n") if p.strip()]
    assert len(text) / len(paragraphs) < audit_lib.UNSTRUCTURED_MEAN_PARAGRAPH_CHARS


def test_reflow_cannot_split_a_block_that_has_no_line_breaks():
    """Stated as a limitation rather than left as a surprise.

    Reflow never invents a break mid-line, because an excerpt has to stay
    verbatim. A single enormous line therefore survives as one paragraph, and
    the only fix for that would be a different extractor.
    """
    one_long_line = "d" * 10_000

    assert audit_lib.reflow_paragraphs(one_long_line) == one_long_line


def test_reflow_is_stable_when_applied_to_its_own_output():
    """Cleaning runs on every ingest, so a second pass must change nothing."""
    raw = "\n".join(f"line {i} of a teacher edition page" for i in range(500))

    once = audit_lib.clean_document_text(raw)
    twice = audit_lib.clean_document_text(once)

    assert once == twice
    assert not audit_lib.looks_unstructured(once)


def test_a_tiny_document_with_no_blank_lines_is_not_made_worse():
    """Below the target size reflow has nothing to do, and must not invent breaks."""
    raw = "One short acknowledgements line."

    assert audit_lib.reflow_paragraphs(raw) == raw
