"""Fast, local PDF extraction adapter.

Lightweight text/table extraction (PyMuPDF/pdfplumber) with OCR and image
extraction disabled. This module does not import any notebook/audit entry point.
"""
from __future__ import annotations

import re
import shutil
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pdfplumber
import pymupdf

from sami.contracts import ConversionRequest, EngineResult, InputError


# Groups quality, OCR, image, table, and coverage-check options.
@dataclass
class Options:
    quality: str = 'balanced'
    ocr: bool | None = None
    images: bool | None = None
    markers: bool | None = None
    table_style: str = 'pipe'
    max_pages: int | None = None
    overwrite: bool = False
    qc_threshold: float = 0.88

    # Normalizes aliases, validates options, and fills defaults by quality tier.
    def resolve(self):
        self.quality = {'1':'fast','2':'balanced','3':'high','draft':'fast','standard':'balanced','fidelity':'high'}.get(self.quality,self.quality)
        if self.quality not in ('fast','balanced','high'): raise ValueError('invalid quality')
        if self.table_style not in ('pipe','html'): raise ValueError('invalid table style')
        if self.max_pages is not None and self.max_pages < 1: raise ValueError('max pages must be positive')
        if self.ocr is None: self.ocr = self.quality == 'high'
        if self.images is None: self.images = self.quality == 'high'
        if self.markers is None: self.markers = self.quality != 'fast'
        return self

# Joins words split across line breaks and normalizes whitespace.
def norm(text):
    return re.sub(r'\s+', ' ', re.sub(r'(?<=\w)-\s*\n\s*(?=\w)', '', text)).strip()

# Extracts lowercase words while preserving internal hyphens and apostrophes.
def words(text): return re.findall(r"\b[\w]+(?:[-’'][\w]+)*\b",text.lower(), re.UNICODE)

# Counts n-word sequences to compare text coverage.
def grams(w,n=4): return Counter(tuple(w[i:i+n]) for i in range(max(0,len(w)-n+1)))

# Calculates the fraction of source elements retained in another counter.
def ratio(a,b):
    if not a: return 1.0
    return sum((a & b).values())/sum(a.values())

# Normalizes cells and renders a table as pipe Markdown or HTML.
def table_md(rows, style):
    rows=[[norm(str(v)) if v is not None else '' for v in r] for r in rows]
    if not rows: return ''
    w=max(map(len,rows))
    rows=[r+['']*(w-len(r)) for r in rows]
    if style=='html':
        from html import escape
        return '<table>\n'+ '\n'.join('<tr>' + ''.join('<td>'+escape(v)+'</td>' for v in r)+'</tr>' for r in rows) + '\n</table>'
    # Escapes pipes and removes line breaks inside a Markdown cell.
    def esc(v): return v.replace('|','\\|').replace('\n',' ')
    return '\n'.join(['| '+' | '.join(map(esc,rows[0]))+' |','| '+' | '.join(['---']*w)+' |'] + ['| '+' | '.join(map(esc,r))+' |' for r in rows[1:]])

# P01/P03: uniform normalization for comparable prose, without treating
# Markdown table separators or line-wrap hyphens as missing text.
# Normalizes Unicode and split words for prose and cell comparisons.
def comparable_tokens(text):
    text = unicodedata.normalize('NFKC', str(text)).replace('\u00ad', '')
    text = re.sub(r'([A-Za-z]{2,})-\s*\n\s*([a-z]{2,})', r'\1\2', text)
    return re.findall(r"\w+(?:[.,]\d+)*", text.casefold(), re.UNICODE)

# Rejoins words hyphenated across two lines.
def repair_hyphens(text):
    return re.sub(r'([A-Za-z]{2,})-\s*\n\s*([a-z]{2,})', r'\1\2', text)

# Recovers positioned lines and estimates reading order in two columns.
def layout_lines(blocks, page_width):
    """Conservative 2-column block ordering; otherwise retain vertical order."""
    items=[]
    for b in blocks:
        if b.get('type') != 0: continue
        for line in b.get('lines', []):
            spans=line.get('spans', [])
            if not spans: continue
            label=''.join(z.get('text','') for z in spans).strip()
            if label: items.append((tuple(line.get('bbox',b['bbox'])), label))
    left=[z for z in items if z[0][2] <= page_width*.53]
    right=[z for z in items if z[0][0] >= page_width*.47]
    split = (len(left)>=5 and len(right)>=5 and
             len(left)+len(right)>=len(items)*.70)
    if split:
        # Full-width headers are kept before the columns only when above body.
        body_top=min(z[0][1] for z in left+right)
        prefix=[z for z in items if z[0][2]>page_width*.53 and z[0][0]<page_width*.47 and z[0][1]<body_top]
        ordered=sorted(prefix,key=lambda z:(z[0][1],z[0][0]))
        used={id(z) for z in ordered}
        ordered += sorted([z for z in left if id(z) not in used],key=lambda z:(z[0][1],z[0][0]))
        used.update(id(z) for z in left)
        ordered += sorted([z for z in right if id(z) not in used],key=lambda z:(z[0][1],z[0][0]))
        used.update(id(z) for z in right)
        # Do not silently lose blocks that span the gutter.
        ordered += sorted([z for z in items if id(z) not in used],key=lambda z:(z[0][1],z[0][0]))
    else:
        ordered=sorted(items,key=lambda z:(z[0][1],z[0][0]))
    return ordered, split

# Groups nearby aligned lines into paragraphs and repairs split words.
def format_prose(items):
    """Conservatively repair wrapped lines inside nearby same-column blocks."""
    if not items: return ''
    groups=[]; current=items[0][1]; previous=items[0][0]
    for bbox,label in items[1:]:
        prior_height=max(1,previous[3]-previous[1]); gap=bbox[1]-previous[3]
        aligned=abs(bbox[0]-previous[0]) < 16
        continuation=aligned and -.5*prior_height <= gap <= 1.1*prior_height
        if continuation and not current.rstrip().endswith((':',';')):
            if re.search(r'[A-Za-z]{2,}-$',current) and re.match(r'[a-z]{2,}',label):
                current=current[:-1]+label
            else: current+=' '+label
        else:
            groups.append(current);current=label
        previous=bbox
    groups.append(current)
    return '\n\n'.join(groups)

# Measures cell-token retention after rendering a table.
def table_token_coverage(rows, rendered):
    source=Counter(t for row in rows for cell in row if cell is not None for t in comparable_tokens(cell))
    # HTML markup and Markdown separator bars should not count as textual cells.
    from html import unescape
    clean=re.sub(r'<[^>]*>', ' ', rendered)
    clean=re.sub(r'^\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*$', '',clean,flags=re.M)
    output=Counter(comparable_tokens(unescape(clean)))
    return ratio(source,output)

# Rasterizes a page, runs Tesseract, and returns text and mean confidence.
def run_ocr_on_page(page, i):
    import pytesseract
    from PIL import Image
    import io
    from pytesseract import Output
    try:
        pix=page.get_pixmap(matrix=pymupdf.Matrix(2,2),alpha=False)
        img=Image.open(io.BytesIO(pix.tobytes('png')))
        data=pytesseract.image_to_data(img,output_type=Output.DICT)
        confs=[float(c) for c,t in zip(data['conf'],data['text']) if t.strip() and float(c)>=0]
        ocr_conf=round(sum(confs)/len(confs),1) if confs else 0.0
        text=pytesseract.image_to_string(img)
        return text, ocr_conf
    except Exception as e:
        return "", 0.0

# Extracts text, headings, tables, and images; applies OCR and records risks and gaps.
def extract_pages(doc, src, opt, asset_dir, stem, on_page=None):
    pages=[]; all_risks=[]; transform=[]; gap_entries=[]; image_count=0; tables_count=0; title=None
    with pdfplumber.open(src) as plumber:
        for i in range(min(doc.page_count,opt.max_pages or doc.page_count)):
            page=doc[i]; blocks=page.get_text('dict')['blocks']; raw=page.get_text('text') or ''
            ordered_lines, two_columns = layout_lines(blocks, page.rect.width)
            table_checks=[]; prose_reference=''; figure_excluded=not opt.images
            page_gaps=[]; page_risks=[]; text=raw; ocr_conf=None

            # Detects pages with little text and decides whether initial OCR is needed.
            is_scanned = len(words(raw)) < 3 and (len(page.get_images()) or len(raw.strip()) == 0)

            if is_scanned:
                if opt.ocr and shutil.which('tesseract'):
                    text, ocr_conf = run_ocr_on_page(page, i)
                    transform.append(f'page {i+1}: reactive OCR applied (scanned page) with confidence {ocr_conf}')
                else:
                    msg=f'[Context gap: page {i+1} is scanned; text not extractable with [OCR Fallback] = off]'
                    page_gaps.append(msg); text=''

            # Records garbled-encoding indicators and possible column issues.
            indicators=re.findall(r'[\ufffd\ue000-\uf8ff]|\(cid:\d+\)',raw)
            if raw and len(indicators)/len(raw)>=0.01: page_risks.append(f'page {i+1}: garbled-encoding indicators ({100*len(indicators)/len(raw):.1f}%)')

            if opt.quality!='high':
                textblocks=[b for b in blocks if b.get('type')==0 and b.get('bbox')]
                for a in textblocks:
                    if any(b is not a and a['bbox'][2]<=b['bbox'][0] and min(a['bbox'][3],b['bbox'][3])-max(a['bbox'][1],b['bbox'][1])>20 for b in textblocks):
                        page_risks.append(f'page {i+1}: possible multi-column layout; reading order not layout-aware at this tier'); break

            # Prepares lines and identifies a possible heading by font size.
            lines=[norm(x) for x in repair_hyphens(text).splitlines() if x.strip()]
            if two_columns: transform.append(f'page {i+1}: conservative two-column ordering applied')
            heading=None
            if opt.quality!='fast' and ocr_conf is None:
                candidates=[]
                for b in blocks:
                    if b.get('type')!=0: continue
                    for ln in b.get('lines',[]):
                        spans=ln.get('spans',[])
                        if not spans: continue
                        s=norm(''.join(z['text'] for z in spans))
                        if s and len(s)<140 and max(z['size'] for z in spans)>=14 and max(z['size'] for z in spans)>11:
                            candidates.append((max(z['size'] for z in spans),s))
                if candidates:
                    size,s=max(candidates)
                    if s in lines:
                        heading=s
                        if title is None: title=s

            # Builds the Markdown body with page/OCR markers and headings.
            parts=[]
            if opt.markers: parts.append(f'<!-- page {i+1} -->')
            if ocr_conf is not None: parts.append(f'<!-- OCR page {i+1} conf={ocr_conf}{" LOW" if ocr_conf<60 else ""} -->')
            if heading and opt.quality!='fast' and lines and heading in lines:
                parts.append(('## ' if title and heading!=title else '# ')+heading)
                lines.remove(heading)

            # Detects tables and combines cells with positioned text without duplication.
            page_tables=[]
            if opt.quality!='fast' and ocr_conf is None:
                try: page_tables=plumber.pages[i].find_tables()
                except Exception as e: transform.append(f'page {i+1}: table detection unavailable ({type(e).__name__})')

            if page_tables:
                # Merge table content with positioned text; do not duplicate cell text.
                located = []
                for b in blocks:
                    if b.get('type') != 0:
                        continue
                    for line in b.get('lines', []):
                        spans = line.get('spans', [])
                        if not spans:
                            continue
                        label = norm(''.join(z.get('text', '') for z in spans))
                        if not label or label == heading:
                            continue
                        bx = line.get('bbox', b.get('bbox'))
                        if not bx:
                            continue
                        cx, cy = (bx[0]+bx[2])/2, (bx[1]+bx[3])/2
                        if any(t.bbox[0] <= cx <= t.bbox[2] and t.bbox[1] <= cy <= t.bbox[3] for t in page_tables):
                            continue
                        located.append((cy, bx[0], label))
                for t in page_tables:
                    try:
                        cells = t.extract()
                        rendered = table_md(cells, opt.table_style) if cells else ''
                        if not rendered:
                            page_gaps.append(f'[Context gap: table on page {i+1} yielded no usable cells]')
                            continue
                        located.append((t.bbox[1], t.bbox[0], rendered))
                        tables_count += 1
                        table_checks.append((cells,rendered))
                    except Exception as exc:
                        page_gaps.append(f'[Context gap: table on page {i+1} could not be converted ({type(exc).__name__})]')
                if two_columns:
                    located.sort(key=lambda item: (0 if item[1] < page.rect.width*.47 else 1, item[0], item[1]))
                else:
                    located.sort(key=lambda item: (item[0], item[1]))
                if located:
                    parts.append('\n\n'.join(item[2] for item in located))
                    prose_reference='\n\n'.join(item[2] for item in located if not item[2].startswith(('| ','<table>')))
                transform.append(f'page {i+1}: converted {sum(1 for item in located if item[2].startswith("| ") or item[2].startswith("<table>"))} table(s)')
            elif lines:
                formatted = format_prose([(b, norm(t)) for b,t in ordered_lines if norm(t) != heading]) if ocr_conf is None else '\n\n'.join(lines)
                parts.append(formatted)
                prose_reference=repair_hyphens(text)
            if not lines and not heading and not page_gaps and not text.strip():
                page_gaps.append(f'[Context gap: page {i+1} has no extractable text]')
            parts.extend(page_gaps)

            # Extracts images as external resources or records their exclusion.
            if opt.images:
                for j,img in enumerate(page.get_images(full=True),1):
                    try:
                        info=doc.extract_image(img[0]); ext=info['ext']; fname=f'p{i+1}_image{j}.{ext}'
                        asset_dir.mkdir(parents=True,exist_ok=True)
                        (asset_dir/fname).write_bytes(info['image'])
                        parts.append(f'![Image from page {i+1}](assets/{stem}/{fname})')
                        image_count+=1
                    except Exception:
                        page_gaps.append(f'[Context gap: image on page {i+1} could not be extracted]')
            elif page.get_images(): transform.append(f'page {i+1}: figures excluded by policy; graphical content not verified')

            all_risks.extend(page_risks)

            # Attempts OCR rescue when initial page coverage is low.
            source_words = words(text)
            projected_words = words('\n\n'.join(parts))
            if opt.ocr and not is_scanned and not page_tables and len(source_words) >= 20 and shutil.which('tesseract'):
                initial_ratio = ratio(grams(source_words), grams(projected_words))
                if initial_ratio < 0.90:
                    ocr_text, ocr_c = run_ocr_on_page(page, i)
                    ocr_lines = [norm(x) for x in ocr_text.splitlines() if x.strip()]
                    ocr_parts = []
                    if opt.markers: ocr_parts.append(f'<!-- page {i+1} (OCR rescue conf={ocr_c}) -->')
                    if ocr_lines: ocr_parts.append('\n\n'.join(ocr_lines))

                    ocr_ratio = ratio(grams(words(ocr_text)), grams(words('\n\n'.join(ocr_parts))))
                    if ocr_ratio > initial_ratio:
                        parts = ocr_parts
                        text = ocr_text
                        ocr_conf = ocr_c
                        transform.append(f'page {i+1}: reactive OCR rescue completed (coverage improved from {initial_ratio:.1%} to {ocr_ratio:.1%})')

            # Accumulates page results and extraction evidence.
            gap_entries.extend(f'page {i+1}: {x}' for x in page_gaps)
            pages.append({'body':'\n\n'.join(parts),'source':norm(text),'gaps':page_gaps,'risk':page_risks,'ocr_conf':ocr_conf,'prose_reference':prose_reference,'tables':table_checks,'figures_excluded':figure_excluded})
            if on_page: on_page(i+1, min(doc.page_count,opt.max_pages or doc.page_count))
    return pages, title, gap_entries,all_risks,transform,image_count,tables_count
def convert(request: ConversionRequest, on_page=None) -> EngineResult:
    """Convert with the reference batch's effective high/no-OCR/no-images profile."""
    options = Options(
        quality="high", ocr=False, images=False, markers=True,
        table_style="pipe", max_pages=None, overwrite=False,
    ).resolve()
    try:
        with pymupdf.open(request.input_path) as document:
            if document.needs_pass:
                raise InputError("PDF is encrypted or requires a password")
            pages, _title, gaps, risks, transformations, image_count, table_count = extract_pages(
                document, request.input_path, options,
                request.staging_dir / "assets" / request.input_path.stem,
                request.input_path.stem,
                on_page=on_page,
            )
    except InputError:
        raise
    except Exception as exc:
        raise InputError(f"could not read PDF: {exc}") from exc

    body = "\n\n".join(page["body"] for page in pages).rstrip() + "\n"
    warnings = [
        {"code": "FIDELITY_RISK", "message": risk}
        for risk in risks
    ]
    warnings.extend(
        {"code": "TRANSFORMATION", "message": change}
        for change in transformations
    )
    return EngineResult(
        markdown=body,
        processed_pages=len(pages),
        warnings=tuple(warnings),
        gaps=tuple({"code": "CONTENT_GAP", "message": gap} for gap in gaps),
        metrics={"tables": table_count, "images": image_count, "engine": "fast"},
    )
