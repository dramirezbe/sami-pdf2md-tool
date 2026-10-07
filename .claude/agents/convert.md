---
name: convert
description: Convert PDF files to Markdown using sami
tools: [Bash, Read]
---

# PDF Conversion Agent

Convert one or more PDF files to Markdown with extracted figures using sami.

## Steps

1. Verify `sami` is installed: `which sami`
2. If not installed, run: `curl -fsSL https://raw.githubusercontent.com/dramirezbe/sami-pdf2md-tool/main/install.sh | bash`
3. Run conversion with the user's requested options
4. Check the output folder for the generated `.md` and figure files
5. Report: pages converted, figures extracted, output location

## Default command

```bash
sami <pdf-files> -o <output-dir>
```

## Available flags

- `--mode fast` or `--mode balanced`
- `--no-strip-refs` (keep references section)
- `--flat` (no subfolder per PDF)
- `-q` (quiet)
- `-o DIR` (output directory)
