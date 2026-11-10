---
name: egm-resolve
description: How the Elephant answers Goldfish findings on a document it helped write - one category per finding, checkable evidence, and exact edits that apply in one place only. Use before submitting a resolution.
license: Apache-2.0
metadata:
  adapted-from: "google/elephant-goldfish-model skills/egm-resolve (Apache-2.0), see app/aeion/goldfish/upstream/NOTICE.md"
---

# Resolve Goldfish findings

The document and its numbered findings are attached. Give every finding exactly one category:

- **CONTEST**: the critique is wrong and you can cite evidence the reviewer could have read (a section,
  a line of the document).
- **ESCALATE**: the critique is wrong but the evidence is outside the document (a convention, a verbal
  decision). The owner settles it.
- **PROPOSE FIX**: the critique is valid. Give an exact edit: `find` is a passage copied character for
  character from the document that occurs exactly once; `replace` is its new text.
- **DECLINE**: a Nit not worth fixing.

Rules:

- A contest must be checkable. "The reviewer misread" is not evidence; a quoted line is.
- Do not add context to the document only to satisfy a reviewer.
- Never contest a comprehension gap: if a fresh reader did not understand it, the text is unclear.
- Never change a severity.
- For every category other than PROPOSE FIX, `find` and `replace` are empty strings.
- The server tells you when a `find` passage does not occur exactly once; copy a longer, unique passage.

Submit one item per finding, all in one call.
