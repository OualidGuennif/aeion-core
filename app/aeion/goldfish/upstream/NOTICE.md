# Elephant-Goldfish Model, vendored

Source: https://github.com/google/elephant-goldfish-model at commit `bdcfe8cdaee99699c4b2cb7ad4e3b2c1a6b56a31` (2026-11-09).
Copyright Google LLC. Licensed under the Apache License, Version 2.0 (see `LICENSE` in this folder).
This is not an officially supported Google product.

What is copied, unchanged: the ten reviewer personas (`agents/`), the execution instructions and the
five document standards (`resources/`), and the skills brainstorm, draft, review, resolve and
review-loop with the design-document template (`skills/`).

What aeion-core changed (Apache-2.0, section 4b): none of these files. aeion-core runs the same method in
a web application instead of an agent harness. A Goldfish is one model call that receives a persona file
verbatim, an adapter note (`app/aeion/goldfish/__init__.py`) and only the document under review, never
the conversation; the Elephant is the conversation that drafts and resolves. Gates are buttons with one
question each.
