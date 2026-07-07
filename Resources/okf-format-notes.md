---
type: reference
title: Open Knowledge Format (OKF) Notes
description: Personal reference summary of the OKF v0.1 spec used to build this bundle.
resource: https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
tags: [okf, meta, reference]
timestamp: 2026-07-07T00:00:00Z
ingested_by: manual
---

# Summary

This bundle is itself an OKF v0.1 bundle: a directory of markdown "concept" files with YAML frontmatter, organized here using the PARA method (see [root index](/index.md)). This document is a hand-written sample used to sanity-check the format before any automated tooling exists.

# Schema

| Field | Required | Notes |
|---|---|---|
| `type` | Yes | Free string, not centrally registered. |
| `title` | Recommended | Display name. |
| `description` | Recommended | One-sentence summary. |
| `resource` | Recommended | Canonical URI for the underlying asset. |
| `tags` | Recommended | YAML list. |
| `timestamp` | Recommended | ISO 8601. |

# Citations

[1] [OKF SPEC.md](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
[2] [How the Open Knowledge Format can improve data sharing](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing)
