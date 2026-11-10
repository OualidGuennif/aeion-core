# Spec: knowledge/components/goldfish.md
"""The Elephant-Goldfish Model in a web application. A Goldfish is one run of the `goldfish` Flue agent:
a fresh context, one vendored persona verbatim, the document under review, never the conversation.
Reviewers run in parallel; a reviewer that fails twice is reported as not run, never as zero findings."""
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..agents import Submit, streaming
from ..llm import LLMError

UPSTREAM = Path(__file__).resolve().parent / "upstream"
REVIEWERS = {
    "egm-design": ("design_critic.md", "Design critic", "Architecture, scale, cost and unmitigated risks"),
    "egm-codebase-details": ("codebase_details.md", "Codebase details", "Fit with the existing system and its files"),
    "egm-zoom-out": ("zoom_out.md", "Zoom out", "Is this the right problem, at the right altitude?"),
    "egm-comprehension": ("comprehension.md", "Comprehension", "Can a newcomer follow it without the conversation?"),
    "egm-implementation-readiness": ("implementation_readiness.md", "Implementation readiness",
                                     "Could someone build it without making a design decision?"),
    "egm-structural": ("structural.md", "Structural", "Is the document complete and in the expected shape?"),
    "egm-inventive-catalyst": ("inventive_catalyst.md", "Inventive catalyst", "Which trade-off is accepted as inevitable?"),
    "egm-style": ("style.md", "Style", "Plain, precise English without filler"),
}
BRAINSTORM_REVIEWERS = ["egm-design", "egm-codebase-details", "egm-zoom-out", "egm-comprehension",
                        "egm-implementation-readiness", "egm-structural", "egm-inventive-catalyst"]
STANDARDS = ["feature-spec-standard", "heilmeier-standard", "implementation-readiness-standard",
             "re-implementation-standard", "zoom-out-standard"]
# The five review stages of egm-review: reviewers, the range they read, and the standard they apply.
STAGES = [
    {"number": 5, "name": "Initial zoom out", "reviewers": ["egm-zoom-out", "egm-inventive-catalyst"], "range": "full",
     "standards": {"egm-zoom-out": "zoom-out-standard"}},
    {"number": 6, "name": "Comprehension test", "reviewers": ["egm-comprehension"], "range": "full", "standards": {},
     "raw": True},
    {"number": 7, "name": "Critic review", "reviewers": ["egm-design", "egm-structural", "egm-style"], "range": "feature",
     "standards": {"egm-design": "feature-spec-standard", "egm-structural": "feature-spec-standard"}},
    {"number": 8, "name": "Intermediate zoom out", "reviewers": ["egm-zoom-out"], "range": "full",
     "standards": {"egm-zoom-out": "zoom-out-standard"}},
    {"number": 9, "name": "Implementation readiness", "reviewers": ["egm-implementation-readiness", "egm-codebase-details",
     "egm-style"], "range": "detailed", "standards": {"egm-implementation-readiness": "implementation-readiness-standard"}},
]
PRESETS = {"interactive": [5, 6, 7, 8, 9], "consolidated": [5, 6, 7, 8, 9], "feature_spec": [5, 6, 7, 8],
           "implementation": [9]}
SPLIT = re.compile(r"^##\s+(Detailed Implementation Plan|Implementation Plan|Work Breakdown|Implementation Steps)\s*$",
                   re.MULTILINE | re.IGNORECASE)


def standard(name):
    if name not in STANDARDS:
        raise ValueError(f"unknown standard {name!r}")
    return (UPSTREAM / "resources/document_standards" / f"{name}.md").read_text(encoding="utf-8")


def numbered(text, start=1, end=None):
    """The lines of a document with their numbers, so a finding can cite them."""
    lines = text.split("\n")
    end = end or len(lines)
    return "\n".join(f"{n:>4}  {lines[n - 1]}" for n in range(start, min(end, len(lines)) + 1))


def split(document):
    """(feature_range, detailed_range) as (first, last) line pairs; detailed is None without a plan."""
    total = document.count("\n") + 1
    found = SPLIT.search(document)
    if not found:
        return (1, total), None
    line = document[:found.start()].count("\n") + 1
    return (1, line - 1), (line, total)


def review_input(mode, document, line_range=None, standard_name=None, context=()):
    """(message, blocks) for one Goldfish: each piece of material appears once, in its own tagged block."""
    blocks = [{"tag": "mode", "body": mode, "trust": "owner"}]
    if standard_name:
        blocks.append({"tag": "target_standard", "body": standard(standard_name), "trust": "owner"})
    for title, text in context:
        blocks.append({"tag": "reading_list_item", "body": f"{title}\n\n{text[:20000]}"})
    if mode == "BRAINSTORM":
        blocks.append({"tag": "feature_concept", "body": document})
        return "Review the attached feature_concept in the attached mode and write your report.", blocks
    first, last = line_range or (1, document.count("\n") + 1)
    blocks.append({"tag": "target_file", "body": f"Lines {first}-{last}, numbered on the left:\n\n{numbered(document, first, last)}"})
    against = " against the attached target_standard" if standard_name else ""
    return f"Review the attached target_file in the attached mode{against} and write your report.", blocks


def run(client, reviewer, mode, document, *, line_range=None, standard_name=None, context=(), on_event=None, session=None):
    """One Goldfish: {reviewer, status, report}. Retried once; a second failure is 'not run'."""
    message, blocks = review_input(mode, document, line_range, standard_name, context)
    last = "no attempt"
    for attempt in range(2):
        if on_event:
            on_event({"type": "reviewer", "reviewer": reviewer, "status": "running", "attempt": attempt + 1})
        try:
            result = client.run("goldfish", message, blocks=blocks, persona=REVIEWERS[reviewer][0],
                                session=f"{session}-{reviewer}" if session else reviewer)
            if result.text.strip():
                if on_event:
                    on_event({"type": "reviewer", "reviewer": reviewer, "status": "completed"})
                return {"reviewer": reviewer, "status": "completed", "report": result.text.strip()}
            last = "empty report"
        except LLMError as error:
            last = error.message
    if on_event:
        on_event({"type": "reviewer", "reviewer": reviewer, "status": "not run", "detail": last})
    return {"reviewer": reviewer, "status": "not run", "report": "", "detail": last}


def run_all(client, reviewers, mode, document, *, line_range=None, standards=None, context=(), on_event=None, session=None):
    """Every reviewer in parallel, each in its own fresh agent; results in the order requested."""
    standards = standards or {}
    with ThreadPoolExecutor(max_workers=min(8, len(reviewers))) as pool:
        futures = [pool.submit(run, client, r, mode, document, line_range=line_range,
                               standard_name=standards.get(r), context=context, on_event=on_event, session=session)
                   for r in reviewers]
        return [f.result() for f in futures]


def _reports(results):
    return "\n\n".join(f"### {REVIEWERS[r['reviewer']][1]} (`{r['reviewer']}`, {r['status']})\n\n"
                        f"{r['report'] or r.get('detail', '')}" for r in results)


def brief(client, hypothesis, results, author, date, notes="", emit=None, session=None):
    """The concepts brief (Markdown), written by the synthesizer agent from the hypothesis and the reports."""
    blocks = [{"tag": "brief_header", "body": f"Author: {author}\nDate: {date}", "trust": "owner"},
              {"tag": "anchored_hypothesis", "body": hypothesis}]
    if notes:
        blocks.append({"tag": "conversation_notes", "body": notes})
    blocks.append({"tag": "goldfish_reports", "body": _reports(results)})
    result = client.run("synthesizer", "Write the concepts brief from the attached hypothesis and Goldfish reports.",
                        blocks=blocks, session=session, **(streaming(emit, "brief_token") if emit else {}))
    if not result.text.strip():
        raise LLMError("contract", "the synthesizer returned an empty brief")
    return result.text.strip()


FINDINGS = {
    "type": "object", "required": ["findings"], "additionalProperties": False,
    "properties": {"findings": {"type": "array", "maxItems": 40, "items": {
        "type": "object", "additionalProperties": False,
        "required": ["title", "severity", "reviewer", "scope", "description", "recommendation"],
        "properties": {"title": {"type": "string", "minLength": 1, "maxLength": 160},
                       "severity": {"enum": ["Blocker", "Major", "Nit"]},
                       "reviewer": {"type": "string", "maxLength": 120},
                       "scope": {"type": "string", "maxLength": 200},
                       "description": {"type": "string", "minLength": 1, "maxLength": 3000},
                       "recommendation": {"type": "string", "maxLength": 3000}}}}}}


def findings(client, target, line_range, results, session=None):
    """Deduplicated findings from a stage's reports, submitted by the consolidator agent under a strict schema."""
    completed = [r for r in results if r["status"] == "completed"]
    if not completed:
        return []
    blocks = [{"tag": "review_target", "body": f"{target}, lines {line_range[0]}-{line_range[1]}", "trust": "owner"},
              {"tag": "goldfish_reports", "body": _reports(completed)}]
    result = client.run("consolidator", "Consolidate the attached Goldfish reports of this stage into findings.",
                        blocks=blocks, submits=[Submit("submit_findings", FINDINGS)], require="submit_findings",
                        session=session)
    order = {"Blocker": 0, "Major": 1, "Nit": 2}
    return sorted(result.submissions["submit_findings"]["findings"], key=lambda f: order[f["severity"]])


def report_markdown(target, line_range, stage, results, items):
    """The Goldfish review report of one stage, rendered by code from the structured findings."""
    icons = {"Blocker": "🔴", "Major": "🟡", "Nit": "🟢"}
    lines = [f"# Goldfish Review Report: {stage}", "", f"**Target:** `{target}` (lines {line_range[0]}-{line_range[1]})", "",
             "## Reviewer Status", "", "| Reviewer | Status |", "| --- | --- |"]
    lines += [f"| `{r['reviewer']}` | {r['status']} |" for r in results]
    lines += ["", "## Prioritized Findings (Blockers -> Major -> Nits)", ""]
    if not items:
        lines.append("No finding." if any(r["status"] == "completed" for r in results) else "No reviewer completed.")
    for index, item in enumerate(items, 1):
        lines += [f"### {index}. {item['title']} - Severity: {icons[item['severity']]} {item['severity']}",
                  f"* **Reviewer Lens:** `{item['reviewer']}`", f"* **Affected Scope:** {item['scope']}",
                  f"* **Discrepancy Description:** {item['description']}",
                  f"* **Rationale & Recommendation:** {item['recommendation']}", ""]
    raw = [r for r in results if r.get("raw") and r["status"] == "completed"]
    for r in raw:
        lines += ["", f"## {REVIEWERS[r['reviewer']][1]}: full report", "", r["report"]]
    return "\n".join(lines).rstrip() + "\n"
