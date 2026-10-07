---
name: install-check
description: Verify sami installation is complete and functional
tools: [Bash, Read]
---

# Installation Check Agent

Verify that sami is correctly installed and all components are operational.

## Checks

1. `which sami` — binary on PATH
2. `sami --help` — runs without error
3. `ls ~/.sami/` — app home exists with bin/, config/, cache/, logs/
4. `ls ~/.sami/bin/llama-server` — llama-server auto-provisioned
5. `ls ~/.sami/config/defaults.yaml` — default config exists (if setup.sh was used)
6. Quick smoke test: `sami test-pdfs/test_document.pdf -o /tmp/sami-check/ -q`
7. Verify output: `/tmp/sami-check/test_document/test_document.md` exists and is non-empty

## Report

- Installation method detected (uv / setup.sh)
- All components present: yes/no
- Smoke test: pass/fail
- Any warnings or missing components
