# Changelog

Every notable change, newest first ([Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
[SemVer](https://semver.org/)). Each change adds its line under Unreleased; `tools/release/release`
dates them at release time. Spec: knowledge/policies/engineering.md

## [Unreleased]

- Æion Core 0.1.0 from Æion Factory 3.0.0: brainstorm (Elephant-Goldfish), spec studio with AxiomSpec gates and
  export for aeion-observability, documentation hub with a cited assistant; twelve Flue agents on
  deepseek-v4.1-flash at maximum reasoning, behind a loopback gateway that keeps the key.
- Hardened before the first push, from an independent review: a patch that still fails its checks is not
  applied and a value outside the AxiomSpec schema is never stored; nothing `axiom check` would refuse is
  saved; gates that did not run are `unknown`; approval needs aeion-observability's catalog; the server
  binds and answers loopback only; a malformed or oversized `Content-Length` is refused on the server and
  the gateway. New tests prove the key never reaches a response and an export loads in
  aeion-observability's own catalog loader.
