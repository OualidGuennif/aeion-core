# Spec: knowledge/components/goldfish.md
"""Section 1, brainstorm (egm-brainstorm): the Elephant agent clarifies the idea one open question at a
time and anchors a hypothesis with its tool; the owner opens the readiness gate; seven Goldfish agents
review it; the synthesizer agent writes the concepts brief, iterated until the owner saves it."""
import re
from datetime import date

from . import goldfish
from .agents import streaming
from .store import StoreError, now

STATES = ("clarify", "reviewing", "brief", "final")
AFTER_REVIEW = ("[aeion-core] The Goldfish review finished and the attached concepts_brief was updated from it. "
                "Follow the after-review step of your skill.")


def create(store, title, idea, author):
    if not idea.strip():
        raise StoreError("describe the idea first")
    name = store.new_name("sessions", title or idea[:40])
    session = {"id": name, "kind": "brainstorm", "title": (title or idea[:60]).strip(), "author": author or "owner",
               "state": "clarify", "messages": [{"role": "user", "content": idea.strip(), "at": now()}],
               "hypothesis": None, "reviews": [], "briefs": [], "feature": None, "created": now()}
    return store.save_session(session)


def _blocks(session, earlier):
    """The earlier conversation and the current brief; the new message is never among them."""
    blocks = []
    if earlier:
        lines = [f"{'Owner' if m['role'] == 'user' else 'Elephant'}: {m['content']}" for m in earlier[-40:]]
        blocks.append({"tag": "conversation", "body": "\n\n".join(lines)})
    if session["hypothesis"]:
        blocks.append({"tag": "anchored_hypothesis", "body": session["hypothesis"]})
    if session["briefs"]:
        blocks.append({"tag": "concepts_brief", "body": session["briefs"][-1]["markdown"]})
    return blocks


def _hypothesis_tool(data, run):
    run.state["hypothesis"] = data["hypothesis"].strip()
    return "Recorded. End your reply by telling the owner the two ways forward: a Goldfish review or more clarification."


def _elephant(store, client, session, message, earlier, emit):
    result = client.run("elephant", message, blocks=_blocks(session, earlier), tools={"anchor_hypothesis": _hypothesis_tool},
                        session=session["id"], **streaming(emit))
    hypothesis = result.state.get("hypothesis")
    if hypothesis:
        session["hypothesis"] = hypothesis
    return result.text, hypothesis


def turn(store, client, name, text, emit=lambda e: None):
    """The owner's message (empty for the first turn, whose message is the idea) and the Elephant's answer."""
    session = store.session(name)
    if session["state"] == "final":
        raise StoreError("this brainstorm is saved; start a new one or a design draft")
    if text and text.strip():
        session["messages"].append({"role": "user", "content": text.strip(), "at": now()})
    if not session["messages"] or session["messages"][-1]["role"] != "user":
        raise StoreError("write a message")
    reply, hypothesis = _elephant(store, client, session, session["messages"][-1]["content"], session["messages"][:-1], emit)
    session["messages"].append({"role": "assistant", "content": reply, "at": now(), "hypothesis": hypothesis})
    store.save_session(session)
    emit({"type": "message", "content": reply, "hypothesis": session["hypothesis"] if hypothesis else None})
    return session


def review(store, client, name, emit=lambda e: None, context=()):
    """The readiness gate's 'Review with Goldfishes': seven fresh reviews of the hypothesis, then the brief."""
    session = store.session(name)
    if not session["hypothesis"]:
        raise StoreError("no anchored hypothesis yet: keep clarifying until the Elephant proposes one")
    session["state"] = "reviewing"
    store.save_session(session)
    try:
        results = goldfish.run_all(client, goldfish.BRAINSTORM_REVIEWERS, "BRAINSTORM", session["hypothesis"],
                                   context=context, on_event=emit, session=name)
        notes = "\n".join(f"- {m['content'][:400]}" for m in session["messages"] if m["role"] == "user")[-4000:]
        emit({"type": "phase", "phase": "synthesizing"})
        markdown = goldfish.brief(client, session["hypothesis"], results, session["author"], date.today().isoformat(),
                                  notes, emit=emit, session=name)
    except Exception:
        session["state"] = "brief" if session["briefs"] else "clarify"
        store.save_session(session)
        raise
    session["reviews"].append({"at": now(), "hypothesis": session["hypothesis"], "results": results})
    session["briefs"].append({"at": now(), "markdown": markdown})
    session["state"] = "brief"
    store.save_session(session)
    emit({"type": "brief", "markdown": markdown, "results": [{k: r[k] for k in ("reviewer", "status")} for r in results]})
    # The Elephant highlights what matters and hands the next move back to the owner.
    emit({"type": "phase", "phase": "the Elephant reads the brief"})
    focus, _ = _elephant(store, client, session, AFTER_REVIEW, session["messages"], emit)
    if focus:
        session["messages"].append({"role": "assistant", "content": focus, "at": now()})
        store.save_session(session)
        emit({"type": "message", "content": focus, "hypothesis": None})
    return session


def edit_brief(store, name, markdown):
    session = store.session(name)
    if not markdown.strip():
        raise StoreError("the brief is empty")
    session["briefs"].append({"at": now(), "markdown": markdown.strip() + "\n", "edited": True})
    return store.save_session(session)


def save(store, name):
    """Step 4 handoff: the brief becomes a feature document Section 2 can specify."""
    session = store.session(name)
    if not session["briefs"]:
        raise StoreError("no concepts brief yet: run the Goldfish review first")
    markdown = session["briefs"][-1]["markdown"]
    heading = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    meta = store.save_feature(heading.group(1).strip() if heading else session["title"], markdown, "brief",
                              f"brainstorm:{name}", name=session.get("feature"))
    session["feature"], session["state"] = meta["id"], "final"
    store.save_session(session)
    return meta


def reopen(store, name):
    session = store.session(name)
    session["state"] = "brief" if session["briefs"] else "clarify"
    return store.save_session(session)
