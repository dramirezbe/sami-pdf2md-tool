---
name: test
description: Run sami test suite on test-pdfs
tools: [Bash, Read]
---

# Test Agent

Run sami against the test PDFs and verify output quality.

## Steps

1. Verify `sami` is installed: `which sami`
2. Convert both test PDFs:
   ```bash
   sami test-pdfs/test_document.pdf test-pdfs/radio_env_5pages.pdf -o /tmp/sami-test/
   ```
3. Verify output exists:
   - `/tmp/sami-test/test_document/test_document.md` + figures
   - `/tmp/sami-test/radio_env_5pages/radio_env_5pages.md` + figures
4. Check markdown is non-empty and contains expected headings
5. Report: pass/fail, pages, figures, throughput

## Expected results

- `test_document.pdf`: 5 pages, 5 figures, ~3.4 KB markdown
- `radio_env_5pages.pdf`: 5 pages, 3 figures, ~25.9 KB markdown
- Exit code 0, 0 failures

## Verified baselines (2026-10-07)

| Machine | CPU cores | test_document.pdf | radio_env_5pages.pdf |
|---------|-----------|-------------------|---------------------|
| ASUS Vivobook (8 cores, Arch) | 7 threads | 2.3s (0.5s/page) | 44.9s (9.0s/page) |
| nexus-rf (4 cores, Ubuntu 24.04) | 3 threads | 59.1s (11.8s/page) | not tested remotely |

Notes:
- First run on a clean machine is slower due to model downloads (~300 MB surya-ocr models)
- `radio_env_5pages.pdf` has complex tables that trigger llama-server OCR (~41s on 8-core)
- Both machines used `curl | bash` install, 102 packages
