# Código de contexto extraído de PDF2MD_caste.ipynb.
# Conserva el orden y la lógica de las cuatro celdas de código originales.
# Las órdenes de instalación de Jupyter se conservan como comentarios.
# Incluye conversión, ejecución por lotes y auditoría; no se adapta su ejecución.
# ============================================================================
# Celda original 1: Dependencias, configuración, extracción PDF, control de calidad y entrada CLI
# ============================================================================

# Instalar dependencias necesarias antes de ejecutar
# !pip install -q PyMuPDF pdfplumber pyyaml pytesseract
# !apt-get install -y -qq tesseract-ocr

"""Single-controller, tool-backed PDF -> Markdown converter (controlled-test build with Reactive OCR)."""
from __future__ import annotations
import argparse, hashlib, importlib.metadata, json, re, shutil, subprocess, sys, tempfile, os, math, unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path


import pymupdf

# Ignore only the known malformed FontBBox warning from pdfminer.
# Keep all other pdfminer diagnostics visible.
import logging

# Filtra únicamente el aviso conocido de FontBBox de pdfminer.
class _FontBBoxWarningFilter(logging.Filter):
    # Decide si un registro se conserva según el logger y el mensaje del aviso.
    def filter(self, record):
        return not (
            record.name == "pdfminer.pdffont"
            and "Could not get FontBBox" in record.getMessage()
        )

# Configura el filtro del logger sin duplicarlo al reevaluar la celda.
_pdfminer_font_logger = logging.getLogger("pdfminer.pdffont")
# Re-running this notebook cell must not accumulate duplicate filters.
for _filter in list(_pdfminer_font_logger.filters):
    if type(_filter).__name__ == "_FontBBoxWarningFilter":
        _pdfminer_font_logger.removeFilter(_filter)
_pdfminer_font_logger.addFilter(_FontBBoxWarningFilter())

import pdfplumber
import yaml

@dataclass
# Agrupa las opciones de calidad, OCR, imágenes, tablas y control de cobertura.
class Options:
    quality: str = 'balanced'
    ocr: bool | None = None
    images: bool | None = None
    markers: bool | None = None
    table_style: str = 'pipe'
    max_pages: int | None = None
    overwrite: bool = False
    qc_threshold: float = 0.88

    # Normaliza alias, valida opciones y completa valores según el nivel de calidad.
    def resolve(self):
        self.quality = {'1':'fast','2':'balanced','3':'high','draft':'fast','standard':'balanced','fidelity':'high'}.get(self.quality,self.quality)
        if self.quality not in ('fast','balanced','high'): raise ValueError('invalid quality')
        if self.table_style not in ('pipe','html'): raise ValueError('invalid table style')
        if self.max_pages is not None and self.max_pages < 1: raise ValueError('max pages must be positive')
        if self.ocr is None: self.ocr = self.quality == 'high'
        if self.images is None: self.images = self.quality == 'high'
        if self.markers is None: self.markers = self.quality != 'fast'
        return self

# Une palabras cortadas por salto de línea y normaliza los espacios del texto.
def norm(text):
    return re.sub(r'\s+', ' ', re.sub(r'(?<=\w)-\s*\n\s*(?=\w)', '', text)).strip()

# Extrae palabras en minúsculas, conservando guiones y apóstrofos internos.
def words(text): return re.findall(r"\b[\w]+(?:[-’'][\w]+)*\b",text.lower(), re.UNICODE)
# Cuenta secuencias de n palabras para comparar la cobertura textual.
def grams(w,n=4): return Counter(tuple(w[i:i+n]) for i in range(max(0,len(w)-n+1)))
# Calcula la proporción de elementos de origen retenidos en otro contador.
def ratio(a,b):
    if not a: return 1.0
    return sum((a & b).values())/sum(a.values())

# Normaliza celdas y convierte una tabla a Markdown de barras o a HTML.
def table_md(rows, style):
    rows=[[norm(str(v)) if v is not None else '' for v in r] for r in rows]
    if not rows: return ''
    w=max(map(len,rows))
    rows=[r+['']*(w-len(r)) for r in rows]
    if style=='html':
        from html import escape
        return '<table>\n'+ '\n'.join('<tr>' + ''.join('<td>'+escape(v)+'</td>' for v in r)+'</tr>' for r in rows) + '\n</table>'
    # Escapa barras y elimina saltos de línea dentro de una celda Markdown.
    def esc(v): return v.replace('|','\\|').replace('\n',' ')
    return '\n'.join(['| '+' | '.join(map(esc,rows[0]))+' |','| '+' | '.join(['---']*w)+' |'] + ['| '+' | '.join(map(esc,r))+' |' for r in rows[1:]])

# P01/P03: uniform normalization for comparable prose, without treating
# Markdown table separators or line-wrap hyphens as missing text.
# Normaliza Unicode y palabras partidas para comparar prosa y celdas.
def comparable_tokens(text):
    text = unicodedata.normalize('NFKC', str(text)).replace('\u00ad', '')
    text = re.sub(r'([A-Za-z]{2,})-\s*\n\s*([a-z]{2,})', r'\1\2', text)
    return re.findall(r"\w+(?:[.,]\d+)*", text.casefold(), re.UNICODE)

# Recompone palabras divididas con guion entre dos líneas.
def repair_hyphens(text):
    return re.sub(r'([A-Za-z]{2,})-\s*\n\s*([a-z]{2,})', r'\1\2', text)

# Recupera líneas con coordenadas y estima el orden de lectura en dos columnas.
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

# Agrupa líneas próximas y alineadas en párrafos, reparando palabras partidas.
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

# Mide la retención de tokens de las celdas tras renderizar la tabla.
def table_token_coverage(rows, rendered):
    source=Counter(t for row in rows for cell in row if cell is not None for t in comparable_tokens(cell))
    # HTML markup and Markdown separator bars should not count as textual cells.
    from html import unescape
    clean=re.sub(r'<[^>]*>', ' ', rendered)
    clean=re.sub(r'^\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*$', '',clean,flags=re.M)
    output=Counter(comparable_tokens(unescape(clean)))
    return ratio(source,output)

# Rasteriza una página, ejecuta Tesseract y devuelve texto y confianza media.
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

# Extrae texto, encabezados, tablas e imágenes; aplica OCR y registra riesgos y vacíos.
def extract_pages(doc, src, opt, asset_dir, stem):
    pages=[]; all_risks=[]; transform=[]; gap_entries=[]; image_count=0; tables_count=0; title=None
    with pdfplumber.open(src) as plumber:
        for i in range(min(doc.page_count,opt.max_pages or doc.page_count)):
            page=doc[i]; blocks=page.get_text('dict')['blocks']; raw=page.get_text('text') or ''
            ordered_lines, two_columns = layout_lines(blocks, page.rect.width)
            table_checks=[]; prose_reference=''; figure_excluded=not opt.images
            page_gaps=[]; page_risks=[]; text=raw; ocr_conf=None

            # Detecta páginas con poco texto y decide si requieren OCR inicial.
            is_scanned = len(words(raw)) < 3 and (len(page.get_images()) or len(raw.strip()) == 0)

            if is_scanned:
                if opt.ocr and shutil.which('tesseract'):
                    text, ocr_conf = run_ocr_on_page(page, i)
                    transform.append(f'page {i+1}: OCR reactivo ejecutado (página escaneada) con confianza {ocr_conf}')
                else:
                    msg=f'[Context gap: page {i+1} is scanned; text not extractable with [OCR Fallback] = off]'
                    page_gaps.append(msg); text=''

            # Registra indicios de codificación dañada y posibles problemas de columnas.
            indicators=re.findall(r'[\ufffd\ue000-\uf8ff]|\(cid:\d+\)',raw)
            if raw and len(indicators)/len(raw)>=0.01: page_risks.append(f'page {i+1}: garbled-encoding indicators ({100*len(indicators)/len(raw):.1f}%)')

            if opt.quality!='high':
                textblocks=[b for b in blocks if b.get('type')==0 and b.get('bbox')]
                for a in textblocks:
                    if any(b is not a and a['bbox'][2]<=b['bbox'][0] and min(a['bbox'][3],b['bbox'][3])-max(a['bbox'][1],b['bbox'][1])>20 for b in textblocks):
                        page_risks.append(f'page {i+1}: possible multi-column layout; reading order not layout-aware at this tier'); break

            # Prepara las líneas e identifica un posible encabezado por tamaño tipográfico.
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

            # Construye el cuerpo Markdown con marcadores de página, OCR y encabezados.
            parts=[]
            if opt.markers: parts.append(f'<!-- page {i+1} -->')
            if ocr_conf is not None: parts.append(f'<!-- OCR page {i+1} conf={ocr_conf}{" LOW" if ocr_conf<60 else ""} -->')
            if heading and opt.quality!='fast' and lines and heading in lines:
                parts.append(('## ' if title and heading!=title else '# ')+heading)
                lines.remove(heading)

            # Detecta tablas y combina sus celdas con el texto posicionado sin duplicarlo.
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

            # Extrae imágenes a recursos externos o registra su exclusión.
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

            # Intenta un rescate por OCR si la cobertura inicial de una página resulta baja.
            source_words = words(text)
            projected_words = words('\n\n'.join(parts))
            if opt.ocr and not is_scanned and not page_tables and len(source_words) >= 20 and shutil.which('tesseract'):
                initial_ratio = ratio(grams(source_words), grams(projected_words))
                if initial_ratio < 0.90:
                    ocr_text, ocr_c = run_ocr_on_page(page, i)
                    ocr_lines = [norm(x) for x in ocr_text.splitlines() if x.strip()]
                    ocr_parts = []
                    if opt.markers: ocr_parts.append(f'<!-- page {i+1} (Rescate OCR conf={ocr_c}) -->')
                    if ocr_lines: ocr_parts.append('\n\n'.join(ocr_lines))

                    ocr_ratio = ratio(grams(words(ocr_text)), grams(words('\n\n'.join(ocr_parts))))
                    if ocr_ratio > initial_ratio:
                        parts = ocr_parts
                        text = ocr_text
                        ocr_conf = ocr_c
                        transform.append(f'page {i+1}: Rescate por OCR Reactivo completado (cobertura mejorada de {initial_ratio:.1%} a {ocr_ratio:.1%})')

            # Acumula el resultado de la página y sus evidencias de extracción.
            gap_entries.extend(f'page {i+1}: {x}' for x in page_gaps)
            pages.append({'body':'\n\n'.join(parts),'source':norm(text),'gaps':page_gaps,'risk':page_risks,'ocr_conf':ocr_conf,'prose_reference':prose_reference,'tables':table_checks,'figures_excluded':figure_excluded})
    return pages, title, gap_entries,all_risks,transform,image_count,tables_count

# Revisa YAML, cobertura de prosa y tablas, imágenes y vacíos; calcula procedencia textual.
def qc(md_path,pages,images,qc_threshold=0.88):
    parsed=md_path.read_text(encoding='utf-8'); issues=[]
    if not parsed.strip(): issues.append('[QC gap: output empty]')
    try:
        _, front, body=parsed.split('---',2)
        yaml.safe_load(front)
    except Exception: issues.append('[QC gap: invalid YAML]')
    unresolved=[]
    ratios=[]
    for i,p in enumerate(pages,1):
        if p['gaps']:
            unresolved.extend(f'page {i}: {gap}' for gap in p['gaps'])
        prose=p.get('prose_reference','')
        # Source and output prose must use the SAME figure/table exclusions.
        # The text reference is extractor-derived, not independent visual truth.
        prose_output=p['body']
        for rows,rendered in p.get('tables',[]):
            prose_output=prose_output.replace(rendered,'')
            tscore=table_token_coverage(rows,rendered)
            if tscore < qc_threshold:
                issues.append(f'[QC gap: page {i} table-cell token coverage {tscore:.1%} (< {qc_threshold:.1%})]')
        a=comparable_tokens(prose)
        b=comparable_tokens(prose_output)
        score=ratio(Counter(a),Counter(b)) if a else 1.0
        ratios.append((i,score))
        if len(a)>=20 and score < qc_threshold:
            issues.append(f'[QC gap: page {i} prose token coverage {score:.1%} (< {qc_threshold:.1%})]')
    source=words(' '.join(p['source'] for p in pages))
    output=words(' '.join(p['body'] for p in pages))
    prov=ratio(grams(output),grams(source)) if len(output)>3 else 1.0
    if any(not p['source'].strip() and not p['gaps'] for p in pages): issues.append('[QC gap: unverified blank extracted page]')
    for image in images:
        if not image.exists(): issues.append(f'[QC gap: missing image {image.name}]')
    return issues,ratios,prov,unresolved

# Coordina la conversión por archivo, publica resultados y recursos y escribe el manifiesto.
def run(paths,output_dir,opt):
    opt.resolve(); out=Path(output_dir).expanduser().resolve(); out.mkdir(parents=True,exist_ok=True)
    probe=out/'.pdf2md_write_test'; probe.write_text('ok'); probe.unlink()
    reports=[]; used=set()
    for original in paths:
        src=Path(original).expanduser().resolve()
        rec={'input':str(src),'status':'SKIPPED','errors':[]}
        if src in used: rec['errors'].append('duplicate input path'); reports.append(rec); continue
        used.add(src)
        try:
            if not src.is_file() or src.stat().st_size==0: raise ValueError('unreadable or empty input')
            with src.open('rb') as stream:
                if stream.read(5) != b'%PDF-':
                    raise ValueError('invalid PDF header')
            with pymupdf.open(src) as doc:
                if doc.needs_pass: raise ValueError('encrypted / password protected')
                stem=src.stem; target=out/(stem+'.md'); n=1
                while target in used or (target.exists() and not opt.overwrite):
                    target=out/f'{stem}_{n}.md'; n+=1
                used.add(target); stem=target.stem
                # Generate entirely in staging; do not disturb existing outputs on failure.
                # Genera y verifica la salida en una carpeta temporal antes de publicarla.
                with tempfile.TemporaryDirectory(prefix='.pdf2md-',dir=out) as staging:
                    stage=Path(staging)
                    staged_asset=stage/'assets'/stem
                    pages,title,gaps,risks,changes,img_count,table_count=extract_pages(doc,src,opt,staged_asset,stem)
                    n_pages=len(pages); text_pages=sum(bool(words(p['source'])) for p in pages)
                    classification='TEXT_NATIVE' if text_pages==n_pages else 'SCANNED' if text_pages==0 else 'MIXED'
                    opts={'source':str(src),'pages':f'{n_pages} / {doc.page_count}','class':classification,'quality_tier':opt.quality,'ocr_used':any(p['ocr_conf'] is not None for p in pages),'images_extracted':img_count,'tables_converted':table_count,'converted':date.today().isoformat(),'gaps':len(gaps),'fidelity_risks':len(risks)}
                    heading=title or src.stem
                    notes=['## Conversion Notes','- Figure policy: graphical figures excluded; their semantic content is not verified. Textual captions are retained when extracted.','### Gaps'] + (['- '+x for x in gaps] or ['- None']) + ['### Fidelity risks'] + (['- '+x for x in risks] or ['- None']) + ['### Transformations'] + (['- '+x for x in changes] or ['- None'])
                    notes += ['- Extraction library: PyMuPDF '+importlib.metadata.version('PyMuPDF'), '- Table detector: pdfplumber '+importlib.metadata.version('pdfplumber')]
                    if opts['ocr_used'] and shutil.which('tesseract'): notes+=['- OCR: Tesseract '+(subprocess.run(['tesseract','--version'],capture_output=True,text=True).stdout.splitlines()[0])]
                    header='---\n'+yaml.safe_dump(opts,sort_keys=False,allow_unicode=True).strip()+'\n---\n'
                    content=header+'\n# '+heading+'\n\n'+ '\n\n'.join(p['body'] for p in pages)+'\n\n'+'\n'.join(notes)+'\n'
                    stage_md=stage/'converted.md'
                    stage_md.write_text(content,encoding='utf-8')
                    assets=list(staged_asset.glob('*')) if staged_asset.exists() else []
                    # Determina el estado PASS, PARTIAL o FAIL y el nombre de salida correspondiente.
                    issues,cover,prov,unresolved=qc(stage_md,pages,assets,opt.qc_threshold)
                    status='FAIL' if issues else 'PARTIAL' if unresolved else 'PASS'
                    # A failed attempt never overwrites a previous successful Markdown.
                    destination=(out/(stem+'.FAILED.md')) if status=='FAIL' else (out/(stem+'.PARTIAL.md')) if status=='PARTIAL' else target
                    if status!='PASS' and destination.exists():
                        k=1
                        while destination.exists():
                            destination=out/f'{stem}.{status}.{k}.md'; k+=1
                    # Every attempt gets immutable, unique image paths. Never replace
                    # assets referenced by a previously committed Markdown document.
                    # Publica imágenes con rutas únicas y revierte sus archivos si falla la escritura final.
                    committed_asset=None
                    if assets:
                        import uuid
                        namespace=f'{stem}-{uuid.uuid4().hex}'
                        old_prefix=f'assets/{stem}/'
                        new_prefix=f'assets/{namespace}/'
                        content=content.replace(old_prefix,new_prefix)
                        stage_md.write_text(content,encoding='utf-8')
                        # Validate the final Markdown (including rewritten paths).
                        issues_after,_,_,_=qc(stage_md,pages,assets,opt.qc_threshold)
                        if issues_after != issues:
                            raise RuntimeError('QC changed after asset path rewriting')
                        committed_asset=out/'assets'/namespace
                        committed_asset.parent.mkdir(parents=True,exist_ok=True)
                        staged_asset.rename(committed_asset)
                    try:
                        os.replace(stage_md,destination)
                    except Exception:
                        # Remove only the new, unreferenced assets on commit failure.
                        if committed_asset is not None:
                            shutil.rmtree(committed_asset)
                        raise
                    target=destination
            rec.update(status=status,output=str(target),pages=n_pages,classification=classification,ocr=opts['ocr_used'],gaps=len(gaps),risks=len(risks),errors=issues+unresolved,coverage=cover,provenance=prov,bytes=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest()[:12])

            # Preserve source PDFs regardless of conversion status.

        except Exception as exc:
            rec.update(status='ERROR',errors=[str(exc)])
        reports.append(rec)
    # Construye el manifiesto global con estados, cobertura, huellas y errores por archivo.
    lines=['# PDF → Markdown Conversion Manifest','',f'- Quality tier: {opt.quality} (OCR: {opt.ocr}, images: {opt.images}, page markers: {opt.markers}, table style: {opt.table_style})',f'- Output directory: {out}',f'- Inputs: {len(reports)} | QC passed: {sum(r["status"]=="PASS" for r in reports)}','- Verification scope: text-token and table-cell consistency against extractor output; rendered-page fidelity and excluded figures are NOT verified.','', '| # | Input | Pages | Output | QC | Gaps | Risks |','|---|---|---:|---|---|---:|---:|']
    for j,r in enumerate(reports,1):
        lines.append(f'| {j} | {Path(r["input"]).name} | {r.get("pages","—")} | {Path(r.get("output", "—")).name} | {r["status"]} | {r.get("gaps","—")} | {r.get("risks","—")} |')
    lines+=['','## Evidence','| Input | Bytes | SHA-256 (first 12) | Lowest page coverage | Body text provenance diagnostic |','|---|---:|---|---|---|']
    for r in reports:
        if 'sha256' in r:
            low=min(r['coverage'],key=lambda t:t[1]) if r['coverage'] else None
            lines.append(f'| {Path(r["input"]).name} | {r["bytes"]} | {r["sha256"]} | {str(low) if low else "n/a"} | {r["provenance"]:.1%} |')
    lines+=['','## Gaps and Failures']
    for r in reports:
        for e in r['errors']:
            lines.append(f'- {Path(r["input"]).name}: {e}')
    if not any(r['errors'] for r in reports):
        lines.append('- None')
    manifest=out/'conversion_manifest.md'
    manifest.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return reports,manifest

# Interpreta argumentos de terminal, construye opciones y comunica el resultado de conversión.
def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('pdfs',nargs='+'); ap.add_argument('--output-dir',default='markdown_output'); ap.add_argument('--quality',default='balanced'); ap.add_argument('--ocr',choices=['on','off']); ap.add_argument('--images',choices=['on','off']); ap.add_argument('--page-markers',choices=['on','off']); ap.add_argument('--table-style',choices=['pipe','html'],default='pipe'); ap.add_argument('--max-pages',type=int); ap.add_argument('--overwrite',action='store_true'); ap.add_argument('--qc-threshold',type=float,default=0.88)
    args_list = [arg for arg in sys.argv[1:] if not arg.startswith('-f') and not arg.endswith('.json') and '/kernels/' not in arg]
    if not args_list:
        print("[Aviso] Se definió la lógica de conversión correctamente. Para usarla en Jupyter/Colab, llama a la función `run()` directamente con los argumentos deseados o ejecuta el script mediante la terminal.")
        return 0
    a=ap.parse_args(args_list); opt=Options(a.quality,None if a.ocr is None else a.ocr=='on',None if a.images is None else a.images=='on',None if a.page_markers is None else a.page_markers=='on',a.table_style,a.max_pages,a.overwrite,a.qc_threshold)
    try: reports,manifest=run(a.pdfs,a.output_dir,opt)
    except (ValueError,RuntimeError,OSError) as e: print(f'[Context gap: {e}]',file=sys.stderr); return 2
    print(manifest.read_text()); return 1 if any(r['status']!='PASS' for r in reports) else 0
# Entrada original: diferencia la ejecución de terminal de la ejecución en un kernel.
if __name__=='__main__':
    if 'ipykernel' not in sys.modules:
        sys.exit(main())
    else:
        main()



# ============================================================================
# Celda original 3: Detección del entorno y preparación de carpetas de entrada y salida
# ============================================================================

# Detect the notebook workspace before searching for PDF files.
import os
import sys
from pathlib import Path

# Selecciona la carpeta de entrada según Colab, Deepnote o el directorio actual.
def detect_pdf_input_dir():
    """Return the input workspace for the current notebook environment."""
    if "google.colab" in sys.modules or "COLAB_RELEASE_TAG" in os.environ:
        return Path("/content")
    if "DEEPNOTE_PROJECT_ID" in os.environ:
        return Path("/work")
    # JetBrains Datalore and local Jupyter use the current notebook directory.
    return Path.cwd()

# Prepara las rutas del entorno y muestra los archivos detectados.
PDF_INPUT_DIR = detect_pdf_input_dir()
PDF_OUTPUT_DIR = PDF_INPUT_DIR / "markdown_output"
PDF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"Input folder: {PDF_INPUT_DIR}")
print(f"Output directory: {PDF_OUTPUT_DIR.resolve()}")
print(f"PDF files found: {sum(p.is_file() and p.suffix.lower() == '.pdf' for p in PDF_INPUT_DIR.iterdir())}")

for file in sorted(PDF_OUTPUT_DIR.glob("*.md")):
    print(file.name)

# ============================================================================
# Celda original 4: Descubrimiento de PDF y ejecución secuencial de la conversión
# ============================================================================

# Enumera los PDF de entrada de forma estable antes de procesarlos.
pdf_files = sorted(
    [
        p for p in Path(PDF_INPUT_DIR).iterdir()
        if p.is_file() and p.suffix.lower() == ".pdf"
    ],
    key=lambda p: (p.name.casefold(), p.name)
)

print(f"Carpeta de entrada: {PDF_INPUT_DIR}")
print(f"Archivos PDF encontrados: {len(pdf_files)}")

# Invoca el conversor con calidad alta, OCR e imágenes desactivados y sobrescritura.
if pdf_files:
    opciones = Options(
        quality="high",
        ocr=False,
        images=False,
        overwrite=True
    )

    reports, manifest = run(
        pdf_files,
        PDF_OUTPUT_DIR,
        opciones
    )

    print("Conversión secuencial finalizada.")
else:
    print("No se encontraron archivos PDF.")

# ============================================================================
# Celda original 5: Auditoría de fidelidad mediante muestreo de documentos y páginas
# ============================================================================

from pathlib import Path
from collections import Counter
import random
import re
import pymupdf

# ============================================================
# 1. CONFIGURATION
# ============================================================

ROOT = Path(PDF_INPUT_DIR) if "PDF_INPUT_DIR" in globals() else Path("/content")
OUTPUT = (
    Path(PDF_OUTPUT_DIR)
    if "PDF_OUTPUT_DIR" in globals()
    else ROOT / "markdown_output"
)

AUDIT_DIR = OUTPUT / "fidelity_audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

NUM_DOCUMENTS = 3
PAGES_PER_DOCUMENT = 3
RANDOM_SEED = 42
QC_THRESHOLD = 0.88

rng = random.Random(RANDOM_SEED)

# ============================================================
# 2. DISCOVER SUCCESSFULLY CONVERTED PDF FILES
# ============================================================

if "reports" not in globals():
    raise RuntimeError(
        "Conversion reports are unavailable. "
        "Execute the PDF conversion cell first."
    )

passed_files = {
    str(Path(r["input"]).resolve())
    for r in reports
    if r.get("status") == "PASS"
}

eligible_pdfs = sorted(
    (
        p for p in ROOT.iterdir()
        if (
            p.is_file()
            and p.suffix.lower() == ".pdf"
            and str(p.resolve()) in passed_files
            and (OUTPUT / f"{p.stem}.md").is_file()
        )
    ),
    key=lambda p: (p.name.casefold(), p.name)
)

if not eligible_pdfs:
    raise RuntimeError(
        "No successfully converted PDFs were found."
    )

# ============================================================
# 3. RANDOM DOCUMENT AND PAGE SELECTION
# ============================================================

selected_pdfs = rng.sample(
    eligible_pdfs,
    min(NUM_DOCUMENTS, len(eligible_pdfs))
)

SAMPLES = {}

for pdf_path in selected_pdfs:

    with pymupdf.open(pdf_path) as doc:
        total_pages = len(doc)

    if total_pages == 0:
        print(f"SKIP: {pdf_path.name} contains no pages.")
        continue

    selected_pages = sorted(
        rng.sample(
            range(1, total_pages + 1),
            min(PAGES_PER_DOCUMENT, total_pages)
        )
    )

    SAMPLES[pdf_path.name] = selected_pages

print("=" * 65)
print("RANDOM FIDELITY AUDIT SAMPLE")
print("=" * 65)

for filename, pages in SAMPLES.items():
    print(f"{filename}")
    print(f"  Selected pages: {pages}")

print(f"\nRandom seed: {RANDOM_SEED}")
print(f"Documents selected: {len(SAMPLES)}")

# ============================================================
# 4. TEXT NORMALIZATION AND COVERAGE
# ============================================================

# Normaliza texto para la auditoría de retención de tokens por página.
def normalize_tokens(text):
    """Normalize extracted text for token-retention comparison."""

    text = re.sub(
        r"(?<=\w)-\s*\n\s*(?=\w)",
        "",
        text
    )

    text = re.sub(r"\s+", " ", text)

    return re.findall(
        r"\w+",
        text.casefold(),
        flags=re.UNICODE
    )


# Compara multiconjuntos de tokens y devuelve cobertura o None si falta texto de origen.
def token_coverage(source, target):
    """Calculate multiset token-retention coverage."""

    source_tokens = Counter(normalize_tokens(source))
    target_tokens = Counter(normalize_tokens(target))

    if not source_tokens:
        return None

    matched = sum(
        (source_tokens & target_tokens).values()
    )

    return matched / sum(source_tokens.values())


# ============================================================
# 5. EXTRACT CORRESPONDING MARKDOWN PAGE
# ============================================================

# Localiza la sección de una página Markdown a partir de sus marcadores numerados.
def extract_md_page(markdown, page_number):
    """
    Extract one Markdown page using page markers.

    Supported examples:
        <!-- Page 3 -->
        ## Page 3
    """

    marker = re.compile(
        r"(?m)^(?:<!--\s*Page\s+(\d+)\s*-->|"
        r"#{1,6}\s+Page\s+(\d+)\s*)$",
        re.IGNORECASE
    )

    matches = list(marker.finditer(markdown))

    for i, match in enumerate(matches):

        number = int(
            match.group(1) or match.group(2)
        )

        if number == page_number:

            end = (
                matches[i + 1].start()
                if i + 1 < len(matches)
                else len(markdown)
            )

            return markdown[match.end():end]

    return None


# ============================================================
# 6. RUN FIDELITY COMPARISON
# ============================================================

results = []

for pdf_name, page_numbers in SAMPLES.items():

    pdf_path = ROOT / pdf_name
    md_path = OUTPUT / f"{pdf_path.stem}.md"

    if not pdf_path.exists() or not md_path.exists():
        print(
            f"SKIP: {pdf_name} — PDF or Markdown missing"
        )
        continue

    markdown = md_path.read_text(
        encoding="utf-8"
    )

    with pymupdf.open(pdf_path) as document:

        for page_number in page_numbers:

            if not 1 <= page_number <= len(document):
                print(
                    f"SKIP: {pdf_name}, invalid page {page_number}"
                )
                continue

            source = document[
                page_number - 1
            ].get_text("text")

            converted = extract_md_page(
                markdown,
                page_number
            )

            if converted is None:

                print(
                    f"UNVERIFIED: {pdf_name}, "
                    f"page {page_number} "
                    "(Markdown page marker not found)"
                )

                results.append({
                    "pdf": pdf_name,
                    "page": page_number,
                    "coverage": None,
                    "status": "UNVERIFIED"
                })

                continue

            score = token_coverage(
                source,
                converted
            )

            if score is None:
                status = "UNVERIFIED"
            elif score >= QC_THRESHOLD:
                status = "PASS"
            else:
                status = "FAIL"

            results.append({
                "pdf": pdf_name,
                "page": page_number,
                "coverage": score,
                "status": status
            })

            score_text = (
                f"{score:.2%}"
                if score is not None
                else "N/A"
            )

            # ------------------------------------------------
            # Generate individual comparison report
            # ------------------------------------------------

            report = (
                "# Fidelity comparison\n\n"
                f"PDF: {pdf_name}\n\n"
                f"Page: {page_number}\n\n"
                f"Random seed: {RANDOM_SEED}\n\n"
                f"Token coverage: {score_text}\n\n"
                f"Status: {status}\n\n"
                "## Original extracted text\n\n"
                f"```\n{source}\n```\n\n"
                "## Converted Markdown\n\n"
                f"```\n{converted}\n```\n"
            )

            destination = (
                AUDIT_DIR /
                f"{pdf_path.stem}_page_{page_number}.md"
            )

            destination.write_text(
                report,
                encoding="utf-8"
            )

            print(
                f"{pdf_path.stem} | "
                f"Page {page_number} | "
                f"Coverage: {score_text} | "
                f"{status}"
            )


# ============================================================
# 7. FINAL AUDIT SUMMARY
# ============================================================

print("\n" + "=" * 65)
print("FIDELITY AUDIT SUMMARY")
print("=" * 65)

counts = Counter(
    r["status"] for r in results
)

print(f"Documents sampled: {len(SAMPLES)}")
print(f"Pages evaluated: {len(results)}")
print(f"PASS: {counts['PASS']}")
print(f"FAIL: {counts['FAIL']}")
print(f"UNVERIFIED: {counts['UNVERIFIED']}")

valid_scores = [
    r["coverage"]
    for r in results
    if r["coverage"] is not None
]

if valid_scores:
    print(
        f"Minimum token coverage: {min(valid_scores):.2%}"
    )
    print(
        f"Average token coverage: "
        f"{sum(valid_scores) / len(valid_scores):.2%}"
    )

print(f"\nComparison reports: {AUDIT_DIR.resolve()}")
