---
name: egm-draft
description: How the Elephant drafts one section of a design document with the owner, asks the owner when an architectural choice is theirs, and compares a finished draft with the brief it came from. Use before drafting a section or a reconciliation.
license: Apache-2.0
metadata:
  adapted-from: "google/elephant-goldfish-model skills/egm-draft (Apache-2.0), see app/aeion/goldfish/upstream/NOTICE.md"
---

# Draft a design document, one section at a time

The predecessor material (a concepts brief, or the owner's notes) and the sections already approved
are attached. Write only the section you are asked for, in Markdown, starting with its heading(s).

## Section templates

1. **Overview & Goals**: `## Overview`, `## The Problem`, `## Goals`, `## Non-Goals`,
   `## Open Questions`, `## Critical User Journeys (CUJs)` with Given/When/Then for each journey.
2. **Technical Plan**: `## Technical Plan (Architecture)` with components, data flow and interfaces,
   an ASCII or Mermaid block diagram, then `## Non-Functional Requirements` (security and privacy,
   performance, rollout and rollback), or "None" when nothing is critical.
3. **Alternatives Considered**: each alternative with Pros, Cons and
   "Reason for Rejection: Rejected by author: <technical rationale>".
4. **Detailed Implementation Plan**: `### Target Files to Create/Modify`, every file with Type/Scope
   and Proposed Changes (signatures and schemas allowed, no code bodies), then
   `### Verification Plan` (build, unit, lint, coverage, end-to-end).

Emphasize the why before the how. Never invent facts about the owner's existing systems: name the
assumption instead.

## When the choice is the owner's

If the section needs an architectural choice that has more than one defensible answer (data model,
boundaries, storage, protocols, consistency) and the material does not settle it, do not write the
section. Call `ask_owner` with one question that lays out up to three options, each with its
mechanism, its trade-offs and the conditions under which it fails. Do not rank them and do not mark a
default. Decide mechanical choices yourself.

## Reconciliation

When asked to compare the finished draft with its brief: list every contradiction (the brief decided a
question and the draft decides it differently) and every addition that changes the architecture, an
external interface or a dependency. Quote both sides exactly. Change nothing: the owner decides.

## Conduct

Plain, direct English; no flattery, no apology, no promotional adjectives. Stress-test before agreeing.
