from bs4 import BeautifulSoup

from sami.scientific_fidelity import missing_tokens, reconcile_labelled_table


def line(y, *items):
    return ([(text, x, x + width) for text, x, width in items], y, y + 5)


def test_rebuilds_labelled_table_using_pdf_values_not_ocr_numbers():
    lines = [
        line(0, ("Method", 10, 20), ("Score", 100, 20), ("Time", 140, 20)),
        line(10, ("Alpha", 10, 20)),
        line(20, ("(1,2,3)", 10, 30), ("47.17", 100, 15), ("43.98", 140, 15)),
        line(30, ("Beta", 10, 15)),
        line(40, ("(1,2,", 10, 25), ("26.21", 100, 15), ("25.26", 140, 15)),
        line(45, ("3,4)", 15, 15)),
    ]
    ocr = """<table><tr><th>Method</th><th>Score</th><th>Time</th></tr>
    <tr><td><b>Alpha</b> (1,2,3)</td><td>47.17</td><td>4.98</td></tr>
    <tr><td><b>Beta</b> (1,2,3,4)</td><td>26.21</td><td>25.26</td></tr></table>"""
    assert missing_tokens(lines, ocr)["43.98"] == 1
    repaired = reconcile_labelled_table(lines, ocr)
    assert repaired and not missing_tokens(lines, repaired)
    table = BeautifulSoup(repaired, "html.parser")
    rows = table.find_all("tr")
    assert [c.get_text(' ', strip=True) for c in rows[1].find_all('td')] == ["Alpha (1,2,3)", "47.17", "43.98"]
    assert "3,4)" in rows[2].get_text(' ')


def test_ambiguous_or_unaligned_tables_are_not_rewritten():
    lines = [line(0, ("Alpha", 10, 20)), line(5, ("1.00", 100, 10)),
             line(10, ("Alpha", 10, 20)), line(15, ("2.00", 100, 10))]
    ocr = '<table><tr><td><b>Alpha</b></td><td>1.00</td></tr><tr><td><b>Alpha</b></td><td>2.00</td></tr></table>'
    assert reconcile_labelled_table(lines, ocr) is None


def test_unresolved_table_keeps_original_and_records_review(monkeypatch):
    import contextlib
    import sys
    import types
    from sami.scientific_fidelity import repair_tables

    source = [line(1, ("Alpha", 10, 20), ("43.98", 100, 20))]
    monkeypatch.setitem(sys.modules, "marker", types.ModuleType("marker"))
    monkeypatch.setitem(sys.modules, "marker.processors", types.ModuleType("marker.processors"))
    monkeypatch.setitem(sys.modules, "marker.processors.table_recon", types.SimpleNamespace(
        table_lines_from_pdftext=lambda *_: source))
    monkeypatch.setattr("sami.ocr_budget.bounded_ocr", lambda *_a, **_kw: contextlib.nullcontext())
    block = types.SimpleNamespace(html=None, structure=[1], text_extraction_method="pdftext",
                                  polygon=types.SimpleNamespace(bbox=[0, 0, 200, 20]))
    page = types.SimpleNamespace(page_id=0, pdftext_page={"blocks": [1]},
                                 contained_blocks=lambda *_: [block])
    document = types.SimpleNamespace(pages=[page])
    class Processor:
        block_types = ()
        def __call__(self, _):
            block.html = "<table><tr><td>4.98</td></tr></table>"
            block.structure = []
        def run_ocr_fallback(self, *_):
            block.html = "<table><tr><td>4.98</td></tr></table>"
    reviews = []
    repair_tables(Processor(), document, lambda *args: reviews.append(args), lambda _: None)
    assert "4.98" in block.html
    assert len(reviews) == 1
    assert reviews[0][0] is page and reviews[0][2] == "table"
    assert "43.98" in reviews[0][4]


def test_algorithm_check_rejects_truncation_and_changed_variable():
    from sami.scientific_fidelity import algorithm_candidate_safe, is_algorithm
    source = "1: Pmin ← 0\n2: Pmax ← 9\n3: Pmid ← 4\n4: return Pmid"
    assert is_algorithm(source)
    assert not is_algorithm("1: First\n2: Second\n4: Fourth\n3: Third")
    assert not algorithm_candidate_safe(source, "<p>1: Pmin 2: Pmax 3: Pmin 4: return Pmin</p>")
    assert not algorithm_candidate_safe(source, "<p>1: Pmin 2: Pmax 3: Pmid</p>")
    assert algorithm_candidate_safe(source, "<p>1: Pmin ← 0 2: Pmax ← 9 3: Pmid ← 4 4: return Pmid</p>")
    assert not algorithm_candidate_safe(source, "<p>1: Pmin ← 0 2: Pmax ← 8 3: Pmid ← 4 4: return Pmid</p>")


def test_numbered_prose_is_not_classified_as_algorithm():
    from sami.scientific_fidelity import is_algorithm
    assert not is_algorithm("1: First topic for readers\n2: Second topic\n3: Third topic\n4: Fourth topic")
    assert is_algorithm("1: for i in range\n2: test\n3: test\n4: return value")


def test_review_appendix_survives_unavailable_markdown_renderer(monkeypatch):
    import sys
    from sami.scientific_fidelity import review_appendix
    monkeypatch.setitem(sys.modules, "marker.renderers.markdown", None)
    result = review_appendix([(4, "algorithm", "review.png", "source 2", "<p>OCR 2</p>")])
    assert "![Original algorithm from page 4](review.png)" in result
    assert "source 2" in result and "OCR 2" in result
    assert "Unverified OCR alternative" in result
    assert review_appendix([]) == ""


def test_algorithm_source_html_keeps_lines_and_escapes_markup():
    from sami.scientific_fidelity import algorithm_source_html
    assert algorithm_source_html("1: a < b\n2: c & d") == "<pre>1: a &lt; b\n2: c &amp; d</pre>"
