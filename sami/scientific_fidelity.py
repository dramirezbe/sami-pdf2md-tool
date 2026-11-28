"""Conservative checks for scientific tables and algorithm blocks."""
from __future__ import annotations

from collections import Counter
from html import escape
import re
import unicodedata

_TOKEN = re.compile(r"[^\W\d_]{2,}|\d+(?:\.\d+)?", re.UNICODE)
_DECIMAL = re.compile(r"^\d+\.\d+$")


def _normalized(text):
    return unicodedata.normalize("NFKC", text).casefold()


def tokens(text):
    return Counter(_TOKEN.findall(_normalized(text)))


def source_text(lines):
    """Text in geometric line order; neighboring fragments may share a line."""
    return "\n".join(" ".join(token[0] for token in sorted(parts, key=lambda p: p[1]))
                     for parts, _y0, _y1 in sorted(lines, key=lambda line: (line[1], min(t[1] for t in line[0]))))


def missing_tokens(lines, html):
    from bs4 import BeautifulSoup
    source = tokens(source_text(lines))
    output = tokens(BeautifulSoup(html or "", "html.parser").get_text(" "))
    return source - output


def reconcile_labelled_table(lines, ocr_html):
    """Use OCR row labels and column structure with values from positioned PDF text.

    Only accept a narrowly verifiable layout: unique bold row labels in the PDF,
    aligned decimal columns on every row and the same number of data columns as
    the OCR table. Anything ambiguous is left for review.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(ocr_html or "", "html.parser")
    table = soup.find("table")
    if not table:
        return None
    rows = []
    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) < 2 or not cells[0].find(["b", "strong"]):
            continue
        label = cells[0].find(["b", "strong"]).get_text(" ", strip=True)
        if not label:
            return None
        rows.append((label, len(cells)))
    if len(rows) < 2 or len({n for _, n in rows}) != 1:
        return None
    ordered = sorted(lines, key=lambda line: (line[1], min(t[1] for t in line[0])))
    anchors = []
    for label, _ in rows:
        matches = [(y0, i) for i, (parts, y0, _y1) in enumerate(ordered)
                   if any(_normalized(t[0].strip()) == _normalized(label) for t in parts)]
        if len(matches) != 1:
            return None
        anchors.append(matches[0][0])
    if anchors != sorted(set(anchors)):
        return None
    groups = []
    for i, start in enumerate(anchors):
        end = anchors[i + 1] if i + 1 < len(anchors) else float("inf")
        groups.append([line for line in ordered if start <= line[1] < end])
    first_decimals = []
    for group in groups:
        decimals = [token[1] for parts, _, _ in group for token in parts
                    if _DECIMAL.fullmatch(_normalized(token[0]).strip())]
        if not decimals:
            return None
        first_decimals.append(min(decimals))
    if max(first_decimals) - min(first_decimals) > 5:
        return None
    first_numeric = min(first_decimals) - 3
    data_rows = []
    starts = []
    for (label, count), group in zip(rows, groups):
        left_lines = []
        right = []
        for parts, y0, _ in group:
            left = sorted((t for t in parts if t[1] < first_numeric), key=lambda t: t[1])
            if left:
                left_lines.append((y0, " ".join(t[0] for t in left)))
            right.extend(t for t in parts if t[1] >= first_numeric)
        right.sort(key=lambda t: t[1])
        columns = []
        for text, x0, x1 in right:
            if not re.fullmatch(r"[\d.,/%+\-–\s]+", _normalized(text)):
                return None
            if not columns or x0 - columns[-1][2] > 8:
                columns.append([text, x0, x1])
            else:
                columns[-1][0] += " " + text
                columns[-1][2] = max(columns[-1][2], x1)
        if len(columns) != count - 1:
            return None
        starts.append([column[1] for column in columns])
        data_rows.append((label, left_lines, [column[0] for column in columns]))
    if any(max(col) - min(col) > 5 for col in zip(*starts)):
        return None
    column_starts = starts[0]
    header = [[] for _ in range(len(column_starts) + 1)]
    for parts, y0, _ in ordered:
        if y0 >= anchors[0]:
            break
        for text, x0, _ in sorted(parts, key=lambda t: t[1]):
            if x0 < first_numeric:
                index = 0
            else:
                index = min(range(len(column_starts)), key=lambda i: abs(column_starts[i] - x0)) + 1
            header[index].append(text)
    if any(not cell for cell in header):
        return None
    output = ["<table><thead><tr>"]
    output.extend(f"<th>{escape(' '.join(cell))}</th>" for cell in header)
    output.append("</tr></thead><tbody>")
    for _label, left_lines, columns in data_rows:
        output.append("<tr><td>" + "<br>".join(escape(text) for _, text in left_lines) + "</td>")
        output.extend(f"<td>{escape(value)}</td>" for value in columns)
        output.append("</tr>")
    output.append("</tbody></table>")
    result = "".join(output)
    # Never silently discard a token present in the available text layer.
    if missing_tokens(lines, result):
        return None
    return result


def repair_tables(processor, document, record_review, log):
    """Retry tables when their reconstruction omits text-layer content."""
    from marker.processors.table_recon import table_lines_from_pdftext
    from sami.ocr_budget import bounded_ocr

    sources = []
    for page in document.pages:
        if not page.pdftext_page:
            continue
        for block in page.contained_blocks(document, processor.block_types):
            if block.html:
                continue
            lines = table_lines_from_pdftext(page.pdftext_page, block.polygon.bbox)
            if lines:
                sources.append((page, block, lines))

    processor(document)
    for page, block, lines in sources:
        if not missing_tokens(lines, block.html):
            continue
        old_html, old_structure, old_method = block.html, block.structure, block.text_extraction_method
        budgets = []
        log(f"Table on page {page.page_id + 1}: checking an OCR reconstruction...")
        try:
            with bounded_ocr([], lambda budget, elapsed: budgets.append((budget, elapsed))):
                processor.run_ocr_fallback(document, [(page, block)])
        except Exception as exc:
            block.html, block.structure, block.text_extraction_method = old_html, old_structure, old_method
            record_review(page, block, "table", f"the second pass failed ({type(exc).__name__})", source_text(lines))
            continue
        candidate = block.html if block.html != old_html else None
        timed_out = any(budget.timed_out for budget, _ in budgets)
        truncated = any(budget.truncated for budget, _ in budgets)
        repaired = reconcile_labelled_table(lines, candidate) if candidate and not timed_out and not truncated else None
        if repaired:
            block.html = repaired
            block.structure = []
            block.text_extraction_method = "pdftext"
            log(f"Table on page {page.page_id + 1}: reconciled OCR layout with PDF text.")
            continue
        # A plausible-looking OCR table may contain wrong values. Keep the
        # original candidate, include the source image/text and flag the gap.
        block.html, block.structure, block.text_extraction_method = old_html, old_structure, old_method
        reason = ("OCR timed out" if timed_out else "OCR was truncated" if truncated
                  else "the table candidates could not be reconciled")
        record_review(page, block, "table", reason, source_text(lines))


_ALGORITHM_LINE = re.compile(r"(?<!\d)(\d{1,3})\s*:")
_IDENTIFIER = re.compile(r"\b[A-Z][A-Za-z0-9]{2,}\b")


def is_algorithm(text):
    numbers = [int(n) for n in _ALGORITHM_LINE.findall(text)]
    return (len(numbers) >= 4 and numbers[0] == 1 and numbers == sorted(set(numbers))
            and ("←" in text or re.search(r"\b(?:while|return|then)\b|\bfor\s+\w+\s*(?:in\b|=|∈)",
                                          text, re.IGNORECASE)))


def algorithm_source_html(source):
    """Keep source line breaks without interpreting document text as HTML."""
    return "<pre>" + escape(source) + "</pre>"


def algorithm_candidate_safe(source, candidate):
    """Reject incomplete OCR and changed named identifiers; not a proof of correctness."""
    from bs4 import BeautifulSoup
    clean = BeautifulSoup(candidate or "", "html.parser").get_text(" ")
    original_numbers = set(_ALGORITHM_LINE.findall(source))
    candidate_numbers = set(_ALGORITHM_LINE.findall(clean))
    if not original_numbers or not original_numbers <= candidate_numbers:
        return False
    original = unicodedata.normalize("NFKC", source)
    generated = unicodedata.normalize("NFKC", clean)
    # Unwrap common TeX subscript syntax before comparing names such as Pmid.
    generated = re.sub(r"[_{}\\]", "", generated)
    names = {value.casefold() for value in _IDENTIFIER.findall(original)}
    detected = {value.casefold() for value in _IDENTIFIER.findall(generated)}
    numbers = Counter(re.findall(r"\d+(?:\.\d+)?", original))
    found_numbers = Counter(re.findall(r"\d+(?:\.\d+)?", generated))
    return names <= detected and not (numbers - found_numbers)


def review_appendix(notes):
    """Keep source and OCR alternatives visible even if Markdown conversion fails."""
    if not notes:
        return ""
    markdown = "\n\n## Areas requiring review\n"
    for page, kind, image_name, source, candidate in notes:
        markdown += f"\n### Page {page}: {kind}\n"
        if image_name:
            markdown += f"\n![Original {kind} from page {page}]({image_name})\n"
        if source:
            markdown += "\nPDF text layer:\n\n```text\n" + source.replace("```", "` ` `") + "\n```\n"
        if candidate:
            try:
                from marker.renderers.markdown import Markdownify
                alternative = Markdownify(
                    False, "", ("$", "$"), ("$$", "$$"), False,
                    heading_style="ATX", bullets="-", escape_misc=False,
                    escape_underscores=True, escape_asterisks=True,
                    escape_dollars=True, sub_symbol="<sub>", sup_symbol="<sup>",
                ).convert(candidate)
            except Exception:
                from bs4 import BeautifulSoup
                alternative = "```text\n" + BeautifulSoup(candidate, "html.parser").get_text("\n").replace("```", "` ` `") + "\n```"
            markdown += "\nUnverified OCR alternative:\n\n" + alternative + "\n"
    return markdown
