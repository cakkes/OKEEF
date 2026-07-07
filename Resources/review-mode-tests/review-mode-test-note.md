---
type: note
title: Review Mode Test Note
description: Note testing AUTO_COMMIT=false review-mode flow in OKEEF.
tags:
- review-mode
- okeef
- test
timestamp: '2026-07-07T14:48:09Z'
source_file: Review Mode Test.txt
ingested_by: okeef-pipeline/0.1
---

# Summary

This note tests the AUTO_COMMIT=false review mode flow for OKEEF.

# Content

This note tests the AUTO_COMMIT=false review-mode flow: it should be staged under
_staging/ rather than filed directly, and should require an explicit `okeef approve`
before it's written to its final location and committed.

# Source

Original file: `Review Mode Test.txt`
Ingested: 2026-07-07T14:48:09Z