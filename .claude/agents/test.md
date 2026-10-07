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

- `test_document.pdf`: 5 pages, 5 figures, ~3 KB markdown
- `radio_env_5pages.pdf`: 5 pages, 3 figures, ~26 KB markdown
- Exit code 0, 0 failures
