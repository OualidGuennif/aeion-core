---
name: egm-synthesis
description: How to merge Goldfish reports into one result - the concepts brief after a brainstorm review, or the deduplicated, severity-ranked findings after a document review stage. Use before writing a brief or submitting findings.
license: Apache-2.0
metadata:
  adapted-from: "google/elephant-goldfish-model agents/synthesizer.md (Apache-2.0), see app/aeion/goldfish/upstream/NOTICE.md"
---

# Synthesize Goldfish reports

The reports are attached; you do not run any reviewer yourself.

## Brainstorm mode: the concepts brief

Deduplicate overlapping points, resolve them into one analysis in plain English, and write the brief
exactly in this Markdown structure, as your whole answer:

```markdown
# [Feature Name]

* **Author:** [author]
* **Date:** [YYYY-MM-DD]

## Overview
## Analysis
## Goals vs. Non-Goals
* **In-Scope Goals:** ...
* **Out-of-Scope Non-Goals:** ...
## Alternatives Weighed
## Key Decisions & Staging for Next Steps
```

Length: the whole brief stays under 1,600 words. It is read by the owner in one sitting and then specified;
completeness comes from naming every objection, not from long paragraphs.

- Overview: the feature, its user and its value, from the anchored hypothesis, in one paragraph.
- Analysis: the objections that recur across reviewers first, then each reviewer's strongest remaining
  objection with the mitigation it requires, two to four sentences each. A reviewer whose
  status is "not run" is listed as not run; never invent its findings.
- Alternatives Weighed: write "Rejected by author: <reason>" only for options the hypothesis or the
  owner rejected in the conversation notes.
- Key Decisions & Staging: what the owner must decide next, in order.

## Review mode: findings

Group the findings by severity (Blocker, Major, Nit). Merge duplicates: keep the strongest severity and
name every reviewer that raised it, comma separated. Keep line references exactly as the reviewers
cited them. Drop nothing a reviewer reported; a "not run" reviewer has no findings. Submit them with
the tool once, complete.

## Conduct

No praise, no buzzwords, no promotional adjectives. Precise nouns, short sentences.
