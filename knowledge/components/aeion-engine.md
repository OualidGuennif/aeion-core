---
type: Component
title: "aeion-core engine"
description: "The local web application: a stdlib Python server with a JSON API and server-sent job events, the workspace store, settings, a safe Markdown renderer and a three-section page."
status: stable
sources:
  - resource: ../../app/serve
    title: "Start script"
  - resource: ../../app/aeion/__init__.py
    title: "Package version"
  - resource: ../../app/tests/support.py
    title: "Shared test fixtures and the scripted upstream"
  - resource: ../../app/aeion/server.py
    title: "HTTP server, routes, jobs, security headers"
  - resource: ../../app/aeion/store.py
    title: "Workspace store"
  - resource: ../../app/aeion/config.py
    title: "Settings and the key reader"
  - resource: ../../app/aeion/markdown.py
    title: "Safe Markdown renderer"
  - resource: ../../app/web/index.html
    title: "Page shell"
  - resource: ../../app/web/app.js
    title: "The three sections"
  - resource: ../../app/web/app.css
    title: "Design system, light and dark"
  - resource: ../../app/tests/test_engine.py
    title: "Server and store tests"
---

# aeion-core engine

## Intent

One local application for the owner: brainstorm a feature, specify it until it passes the template's
gates, export the Markdown file aeion-observability builds, and read every document with a cited
assistant. It runs with `python3 app/serve` and a browser; the agents need Node for Flue.

## Data sources

Settings come from the environment: `AEION_DATA` (workspace, default `workspace/`, ignored by Git),
`AEION_OBSERVABILITY` (default `../aeion-observability`, read only), `AEION_HOST`/`AEION_PORT`
(default `127.0.0.1:8765`), `AEION_MODEL`, `AEION_LLM` (`flue`, or `mock` offline).

## Inputs

JSON requests from the page. Writes are `POST`/`PUT` with the `X-Aeion: 1` header and a JSON body of at
most 2 MB. Long work runs as a job whose events stream at `GET /api/jobs/<id>/events`.

## Outputs

Sessions (`workspace/sessions`, `workspace/studio`), feature documents (`workspace/features`), product
specifications and exports (`workspace/products/<name>`), all written atomically.

## Invariants

- The server listens on loopback and refuses a foreign `Host` header (DNS rebinding).
- A write without the custom header or a JSON body is refused (cross-site requests).
- A name becomes a path only after `[a-z0-9][a-z0-9-]{0,79}` matches it.
- The key, a stack trace or provider internals never reach a response.
- The page loads under a strict Content-Security-Policy; model text is escaped before rendering; only
  the server's Markdown renderer emits HTML, and it refuses unsafe links.

## Determinism

The same workspace and the same requests give the same stored files, apart from timestamps and the
model's text.

## Acceptance checks

- [ ] `python3 -m unittest discover -s app/tests` passes.
- [ ] `python3 app/serve` prints the address and whether the agents are ready.

## Out of scope

Multi-user access, authentication beyond loopback, and writing into aeion-observability.
