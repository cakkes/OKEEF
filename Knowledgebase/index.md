---
okf_version: "0.1"
title: OKEEF
description: Jojo's personal knowledgebase (Open Knowledge Format + PARA method).
timestamp: 2026-07-07T00:00:00Z
---

# OKEEF

Personal second-brain knowledgebase, built on Google's Open Knowledge Format (OKF v0.1) and organized with the PARA method.

# Sections

* [Projects](/Projects/index.md) - active, time-bound efforts with a defined outcome.
* [Areas](/Areas/index.md) - ongoing responsibilities with no end date.
* [Resources](/Resources/index.md) - reference material and topics of interest.
* [Archives](/Archives/index.md) - inactive items from the other three sections.

# How this bundle is built

New material is dropped into `_inbox/`. A local pipeline (Ollama + a small classifier model) extracts, classifies, and files it into the correct section above as a conformant OKF concept document, then commits the result to git. See `log.md` for the change history.
