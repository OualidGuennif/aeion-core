"use strict";
// Æion Core: three sections on one page. Model text is always escaped before it reaches the DOM; the only
// HTML inserted as-is comes from the server's Markdown renderer, which is safe by construction.

const $ = (selector, root = document) => root.querySelector(selector);
const main = () => $("#main");

function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "html") node.innerHTML = value; // server-rendered, already escaped
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function toast(message) {
  const box = $("#toast");
  box.textContent = message;
  box.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => box.classList.remove("show"), 3800);
}

async function api(method, path, body) {
  const options = { method, headers: { Accept: "application/json" } };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.headers["X-Aeion"] = "1";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.message || `request failed (${response.status})`);
  return data;
}

function follow(job, handlers = {}) {
  // Read a background job's events; resolve with its result, reject with its error message.
  return new Promise((resolve, reject) => {
    const source = new EventSource(`/api/jobs/${job}/events`);
    source.onmessage = (message) => {
      const event = JSON.parse(message.data);
      if (handlers[event.type]) handlers[event.type](event);
      if (handlers.any) handlers.any(event);
      if (event.type === "done") { source.close(); resolve(event.result); refreshStatus(); }
      if (event.type === "error") { source.close(); reject(new Error(event.message)); refreshStatus(); }
    };
    source.onerror = () => { source.close(); reject(new Error("the connection to the server was lost")); };
  });
}

// A small Markdown renderer for streamed model text: escape first, then a few block and inline rules.
function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function inlineMd(text) {
  let out = escapeHtml(text);
  out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/(^|[^*\w])\*([^*\s][^*]*?)\*(?!\w)/g, "$1<em>$2</em>");
  out = out.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+|#\/[^\s)]+)\)/g, (m, label, url) =>
    `<a href="${url}"${url.startsWith("http") ? ' target="_blank" rel="noopener"' : ""}>${label}</a>`);
  return out;
}
function md(text) {
  const lines = String(text || "").replace(/\r/g, "").split("\n");
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    if (line.trim().startsWith("```")) {
      const block = []; i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) block.push(lines[i++]);
      i++;
      out.push(`<pre><code>${escapeHtml(block.join("\n"))}</code></pre>`);
      continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) { const n = Math.min(heading[1].length + 1, 6); out.push(`<h${n}>${inlineMd(heading[2])}</h${n}>`); i++; continue; }
    if (/^\s*\|/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      const cells = (row) => row.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const head = cells(line); i += 2; const rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(cells(lines[i++]));
      out.push(`<div class="table"><table><thead><tr>${head.map((c) => `<th>${inlineMd(c)}</th>`).join("")}</tr></thead><tbody>${
        rows.map((r) => `<tr>${r.map((c) => `<td>${inlineMd(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
      continue;
    }
    if (/^\s*([-*+]|\d+[.)])\s+/.test(line)) {
      const ordered = /^\s*\d/.test(line); const items = [];
      while (i < lines.length && (/^\s*([-*+]|\d+[.)])\s+/.test(lines[i]) || (/^\s{2,}\S/.test(lines[i]) && items.length))) {
        const item = lines[i].match(/^\s*([-*+]|\d+[.)])\s+(.*)$/);
        if (item) items.push(item[2]); else items[items.length - 1] += " " + lines[i].trim();
        i++;
      }
      const tag = ordered ? "ol" : "ul";
      out.push(`<${tag}>${items.map((t) => `<li>${inlineMd(t)}</li>`).join("")}</${tag}>`);
      continue;
    }
    if (line.startsWith(">")) {
      const quote = [];
      while (i < lines.length && lines[i].startsWith(">")) quote.push(lines[i++].replace(/^>\s?/, ""));
      out.push(`<blockquote>${md(quote.join("\n"))}</blockquote>`);
      continue;
    }
    const paragraph = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|```|\s*([-*+]|\d+[.)])\s|\s*\||>)/.test(lines[i])) paragraph.push(lines[i++]);
    if (!paragraph.length) paragraph.push(lines[i++]);
    out.push(`<p>${paragraph.map(inlineMd).join("<br>")}</p>`);
  }
  return out.join("\n");
}
const mdNode = (text, cls = "doc") => h("div", { class: cls, html: md(text) });

function download(name, text, type = "text/markdown") {
  const url = URL.createObjectURL(new Blob([text], { type: `${type};charset=utf-8` }));
  const link = h("a", { href: url, download: name });
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

const LENSES = {
  "egm-design": "Design critic", "egm-codebase-details": "Codebase details", "egm-zoom-out": "Zoom out",
  "egm-comprehension": "Comprehension", "egm-implementation-readiness": "Implementation readiness",
  "egm-structural": "Structural", "egm-inventive-catalyst": "Inventive catalyst", "egm-style": "Style",
};
// What an agent's tool call means to the owner, for progress lines.
const TOOL_WORDS = { activate_skill: "reading its method", list_catalog: "reading the build factory's catalog",
  submit_fragment: "checking the draft against the gates", amend_fragment: "fixing what the gates refused",
  submit_patch: "checking the change", read_record: "reading a record", run_checks: "running the checks",
  submit_views: "rendering diagrams", submit_findings: "consolidating findings", submit_resolution: "checking the edits",
  submit_reconciliation: "comparing", anchor_hypothesis: "anchoring the hypothesis", ask_owner: "preparing a question" };
function agentProgress(show) {
  // Handlers that turn reasoning and tool events into one short progress line.
  let tool = "";
  return {
    agent_tool: (e) => { tool = TOOL_WORDS[e.name] || e.name; show(tool); },
    thinking: (e) => show(`${tool ? tool + " · " : ""}reasoning (${e.chars.toLocaleString()} characters)`),
    phase: (e) => show(e.phase),
  };
}
const chip = (text, state = "") => h("span", { class: `chip ${String(state).replace(/\s+/g, "-")}` }, text);

// ---------- status bar ----------
async function refreshStatus() {
  try {
    const s = await api("GET", "/api/status");
    const box = $("#status");
    box.replaceChildren(
      h("span", { title: s.ready ? "Flue agents, reasoning at maximum" : s.problem || "" },
        h("span", { class: `dot ${s.ready ? "on" : ""}` }), `${s.model} · ${s.ready ? "max reasoning" : "not ready"}`),
      h("span", { title: `${s.meter.input_tokens} in · ${s.meter.output_tokens} out` },
        `${s.meter.calls} calls · $${s.meter.estimated_usd.toFixed(4)}`),
      h("span", { title: "aeion-observability catalog (read-only)" },
        s.observability.available ? `catalog ${s.observability.features}` : "catalog offline"));
    refreshStatus.last = s;
  } catch (error) { /* the next poll retries */ }
}

// ---------- router ----------
function route() {
  const hash = location.hash || "#/brainstorm";
  const [, section, ...rest] = hash.split("/");
  const id = decodeURIComponent(rest.join("/"));
  document.querySelectorAll(".tabs a").forEach((a) => a.classList.toggle("on", a.dataset.tab === section));
  if (section === "studio") return studio(id);
  if (section === "docs") return docs(id);
  return brainstormSection(id);
}

// ---------- Section 1: brainstorm, draft, review ----------
async function sidebarSessions(active) {
  const [{ sessions }, { features }] = await Promise.all([api("GET", "/api/sessions"), api("GET", "/api/features")]);
  const kinds = { brainstorm: "Brainstorm", draft: "Design draft", review: "Review" };
  return h("aside", { class: "side" },
    h("button", { class: "btn primary", style: "width:100%", onclick: () => { location.hash = "#/brainstorm/new"; } }, "＋ New brainstorm"),
    h("h3", {}, "Conversations"),
    sessions.length ? sessions.map((s) => h("a", { class: `item ${s.id === active ? "on" : ""}`, href: `#/brainstorm/${s.id}` },
      s.title || s.id, h("small", {}, `${kinds[s.kind] || s.kind} · ${s.state}`))) : h("p", { class: "muted small" }, "None yet."),
    h("h3", {}, "Saved features"),
    features.length ? features.map((f) => h("a", { class: `item ${"feature:" + f.id === active ? "on" : ""}`, href: `#/brainstorm/feature:${f.id}` },
      f.title, h("small", {}, `${f.kind} · ${(f.saved || "").slice(0, 10)}`))) : h("p", { class: "muted small" }, "Save a brief to see it here."));
}

async function brainstormSection(id) {
  const side = await sidebarSessions(id);
  if (!id || id === "new") return main().replaceChildren(h("div", { class: "layout" }, side, newBrainstorm()));
  if (id.startsWith("feature:")) return main().replaceChildren(h("div", { class: "layout" }, side, await featureView(id.slice(8))));
  const session = await api("GET", `/api/sessions/${id}`);
  const view = session.kind === "draft" ? draftView : session.kind === "review" ? reviewView : brainstormView;
  return view(session, side);
}

const pendingTurns = {};
function newBrainstorm() {
  const title = h("input", { type: "text", placeholder: "Webhook delivery for partners" });
  const idea = h("textarea", { rows: 7, placeholder: "Describe the idea in your own words: who needs it, what goes wrong today, what success looks like." });
  const author = h("input", { type: "text", value: "owner" });
  const start = h("button", { class: "btn primary", onclick: async () => {
    if (!idea.value.trim()) return toast("Describe the idea first.");
    start.disabled = true;
    try {
      const { session, job } = await api("POST", "/api/brainstorms", { title: title.value, idea: idea.value, author: author.value });
      pendingTurns[session.id] = job; // the session view streams the Elephant's first answer
      location.hash = `#/brainstorm/${session.id}`;
    } catch (error) { toast(error.message); start.disabled = false; }
  } }, "Start brainstorming");
  return h("section", { class: "pane" }, h("div", { class: "narrow" },
    h("h1", {}, "Brainstorm a feature"),
    h("p", { class: "lead" }, "Design with an elephant, review with goldfish. The Elephant questions the idea until it is clear; seven fresh Goldfish reviewers then challenge it without the conversation, and you save the agreed brief as a feature."),
    h("div", { class: "card" }, h("label", {}, "Working title"), title, h("label", {}, "The idea"), idea,
      h("label", {}, "Author"), author, h("div", { class: "row", style: "margin-top:16px" }, start))));
}

function thread(messages) {
  return h("div", { class: "thread" }, messages.map((m) => h("div", { class: `msg ${m.role}` },
    m.role === "user" ? h("div", {}, m.content) : mdNode(m.content, ""))));
}

function composer(placeholder, send) {
  const box = h("textarea", { rows: 2, placeholder });
  const button = h("button", { class: "btn primary", onclick: () => submit() }, "Send");
  async function submit() {
    const text = box.value.trim();
    if (!text) return;
    button.disabled = true;
    try { await send(text); box.value = ""; } catch (error) { toast(error.message); } finally { button.disabled = false; }
  }
  box.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(); });
  return h("div", { class: "composer" }, h("div", { class: "box" }, box, button), h("div", { class: "muted small", style: "margin:6px 4px" }, "⌘/Ctrl + Enter to send"));
}

function streamingBubble(container) {
  // Streams an agent's answer: a reasoning indicator until text arrives; a later model turn restarts the text.
  const bubble = h("div", { class: "msg assistant typing" }, h("span", { class: "muted small" }, "Thinking…"));
  container.append(bubble);
  let text = "";
  const show = () => { bubble.innerHTML = md(text); bubble.scrollIntoView({ block: "end" }); };
  return {
    add: (chunk) => { text += chunk; show(); },
    reset: () => { text = ""; show(); },
    thinking: (chars) => { if (!text) bubble.replaceChildren(h("span", { class: "muted small" }, `Thinking… ${chars.toLocaleString()} characters of reasoning`)); },
    done: () => bubble.classList.remove("typing"),
    handlers() { return { token: (e) => this.add(e.text), restart: () => this.reset(), thinking: (e) => this.thinking(e.chars) }; },
  };
}

function brainstormView(session, side) {
  const brief = session.briefs.length ? session.briefs[session.briefs.length - 1].markdown : "";
  const messages = h("div", {}, thread(session.messages));
  const lensBox = h("div", { class: "chips" });
  const briefBox = h("div", { class: "doc", html: md(brief) });
  const center = h("section", { class: "pane" }, h("div", { class: "narrow" },
    h("div", { class: "row" }, h("h1", { class: "grow" }, session.title), chip(session.state, session.state === "final" ? "done" : "on")),
    h("p", { class: "lead" }, "The Elephant asks one open question at a time and challenges the idea before agreeing."),
    messages,
    session.hypothesis && session.state !== "final" ? h("div", { class: "card accent" },
      h("h4", {}, "Anchored feature hypothesis"), h("p", {}, session.hypothesis),
      h("div", { class: "row" },
        h("button", { class: "btn primary", onclick: (e) => review(e.target) }, session.briefs.length ? "Re-run the Goldfish review" : "Review with Goldfishes"),
        h("button", { class: "btn", onclick: () => $(".composer textarea").focus() }, "Clarify additional constraints in chat")),
      h("div", { style: "margin-top:12px" }, lensBox)) : null,
    session.state === "final" ? h("div", { class: "card" }, h("h4", {}, "Saved as a feature"),
      h("div", { class: "row" }, h("a", { class: "btn", href: `#/brainstorm/feature:${session.feature}` }, "Open the feature"),
        h("a", { class: "btn primary", href: `#/studio/new:${session.feature}` }, "Specify it in the studio →"),
        h("button", { class: "btn ghost", onclick: async () => { await api("POST", `/api/brainstorms/${session.id}/reopen`, {}); route(); } }, "Reopen"))) :
      composer("Answer the Elephant, or add constraints…", async (text) => {
        messages.querySelector(".thread").append(h("div", { class: "msg user" }, text));
        const bubble = streamingBubble(messages.querySelector(".thread"));
        const { job } = await api("POST", `/api/brainstorms/${session.id}/message`, { text });
        await follow(job, bubble.handlers());
        bubble.done(); route();
      })));
  async function review(button) {
    button.disabled = true;
    lensBox.replaceChildren(...Object.keys(LENSES).filter((k) => k !== "egm-style").map((k) => { const c = chip(LENSES[k], "running"); c.dataset.r = k; return c; }));
    briefBox.innerHTML = ""; let streamed = "", thinkingChip = null;
    try {
      const { job } = await api("POST", `/api/brainstorms/${session.id}/review`, {});
      await follow(job, {
        reviewer: (e) => { const c = lensBox.querySelector(`[data-r="${e.reviewer}"]`); if (c) c.className = `chip ${e.status.replace(/\s+/g, "-")}`; },
        phase: (e) => lensBox.append(chip(e.phase, "running")),
        brief_token: (e) => { streamed += e.text; briefBox.innerHTML = md(streamed); },
        restart: (e) => { if (e.stream === "brief_token") { streamed = ""; briefBox.innerHTML = ""; } },
        thinking: (e) => {
          if (streamed) return;
          thinkingChip = thinkingChip || lensBox.appendChild(chip("", "running"));
          thinkingChip.textContent = `reasoning · ${e.chars.toLocaleString()} characters`;
        },
      });
      route();
    } catch (error) { toast(error.message); button.disabled = false; }
  }
  const editor = h("textarea", { rows: 24, class: "hidden" }, brief);
  const right = h("aside", { class: "pane split" },
    h("div", { class: "row" }, h("h2", { class: "grow", style: "margin:0" }, "Concepts brief"),
      brief ? h("button", { class: "btn small", onclick: () => { editor.classList.toggle("hidden"); briefBox.classList.toggle("hidden"); } }, "Edit") : null),
    brief ? null : h("p", { class: "muted" }, "The brief appears here after the Goldfish review."),
    briefBox, editor,
    brief ? h("div", { class: "row", style: "margin-top:16px" },
      h("button", { class: "btn small", onclick: async () => { await api("PUT", `/api/brainstorms/${session.id}/brief`, { markdown: editor.value }); toast("Brief saved."); route(); } }, "Save edits"),
      session.state !== "final" ? h("button", { class: "btn primary small", onclick: async () => { const f = await api("POST", `/api/brainstorms/${session.id}/save`, {}); toast(`Saved: ${f.title}`); route(); } }, "Save as feature") : null,
      session.feature ? h("button", { class: "btn small", onclick: () => startDraft(session.feature) }, "Draft a design document") : null) : null);
  main().replaceChildren(h("div", { class: brief || session.state === "reviewing" ? "layout three" : "layout" }, side, center, brief || session.state === "reviewing" ? right : null));
  const waiting = pendingTurns[session.id];
  if (waiting) {
    delete pendingTurns[session.id];
    const bubble = streamingBubble(messages.querySelector(".thread"));
    follow(waiting, bubble.handlers()).then(() => route()).catch((e) => { bubble.done(); toast(e.message); });
  }
}

async function startDraft(feature) {
  try { const draft = await api("POST", "/api/drafts", { feature }); location.hash = `#/brainstorm/${draft.id}`; } catch (e) { toast(e.message); }
}

async function featureView(name) {
  const { meta, html } = await api("GET", `/api/features/${name}`);
  const preset = h("select", {}, ...[["interactive", "Interactive, all five stages"], ["consolidated", "Consolidated report, all stages"],
    ["feature_spec", "Feature spec only (stages 5-8)"], ["implementation", "Implementation plan only (stage 9)"]].map(([v, t]) => h("option", { value: v }, t)));
  return h("section", { class: "pane" }, h("div", { class: "narrow" },
    h("div", { class: "row" }, h("h1", { class: "grow" }, meta.title), chip(meta.kind, "on")),
    h("p", { class: "lead" }, `${meta.bytes} bytes · saved ${meta.saved} · from ${meta.origin}`),
    h("div", { class: "card" }, h("div", { class: "row" },
      h("a", { class: "btn primary", href: `#/studio/new:${meta.id}` }, "Specify in the studio →"),
      h("button", { class: "btn", onclick: () => startDraft(meta.id) }, "Draft a design document"),
      h("div", { class: "grow" }), preset,
      h("button", { class: "btn", onclick: async () => { try { const r = await api("POST", "/api/reviews", { feature: meta.id, preset: preset.value }); location.hash = `#/brainstorm/${r.id}`; } catch (e) { toast(e.message); } } }, "Review with Goldfishes"))),
    h("div", { class: "card doc", html })));
}

function draftView(session, side) {
  const names = session.sections.map((s) => s.name);
  const current = session.sections[session.current];
  const live = h("div", { class: "doc" });
  const instruction = h("textarea", { rows: 3, placeholder: "Revisions, or your answer to the Elephant's question…" });
  async function run(text) {
    live.innerHTML = ""; let streamed = "";
    try {
      const { job } = await api("POST", `/api/drafts/${session.id}/section`, { instruction: text || "" });
      await follow(job, { ...agentProgress((text) => { if (!streamed) live.replaceChildren(h("p", { class: "muted small" }, text)); }),
        token: (e) => { streamed += e.text; live.innerHTML = md(streamed); },
        restart: () => { streamed = ""; live.innerHTML = ""; } });
      route();
    } catch (error) { toast(error.message); }
  }
  const body = [];
  if (current) {
    if (current.status === "question") body.push(h("div", { class: "card warn" }, h("h4", {}, "The Elephant needs your decision"), mdNode(current.question, "")));
    if (current.markdown) body.push(h("div", { class: "card doc", html: md(current.markdown) }));
    body.push(live, h("div", { class: "card" }, instruction, h("div", { class: "row", style: "margin-top:10px" },
      h("button", { class: "btn", onclick: () => run(instruction.value) }, current.markdown || current.status === "question" ? "Redraft with this" : "Draft this section"),
      current.status === "drafted" ? h("button", { class: "btn primary", onclick: async () => { await api("POST", `/api/drafts/${session.id}/approve`, {}); route(); } }, `Approve ${current.name}`) : null)));
  } else {
    const verdict = h("div", {});
    body.push(h("div", { class: "card accent" }, h("h4", {}, "Every section is approved"),
      h("p", {}, "Check the draft against the brief it came from, then save it as a design feature."),
      h("div", { class: "row" },
        h("button", { class: "btn", onclick: async (e) => { e.target.disabled = true; const { job } = await api("POST", `/api/drafts/${session.id}/reconcile`, {}); const r = await follow(job).catch((x) => toast(x.message));
          if (!r) return; verdict.replaceChildren(h("h4", {}, `${r.contradictions.length} contradiction(s), ${r.additions.length} addition(s)`),
            ...[...r.contradictions, ...r.additions].map((c) => h("div", { class: "card" }, h("p", {}, h("strong", {}, "Brief: "), c.brief), h("p", {}, h("strong", {}, "Draft: "), c.draft), h("p", { class: "muted" }, c.question)))); } }, "Compare with the brief"),
        session.state === "final" ? h("a", { class: "btn primary", href: `#/studio/new:${session.feature}` }, "Specify it in the studio →") :
          h("button", { class: "btn primary", onclick: async () => { const f = await api("POST", `/api/drafts/${session.id}/save`, {}); toast(`Saved: ${f.title}`); route(); } }, "Save the design")), verdict));
  }
  const approved = session.sections.filter((s) => s.status === "approved");
  main().replaceChildren(h("div", { class: "layout" }, side, h("section", { class: "pane" }, h("div", { class: "narrow" },
    h("div", { class: "row" }, h("h1", { class: "grow" }, session.title), chip(session.state, "on")),
    h("p", { class: "lead" }, "Section by section, with your approval at each gate. Architectural choices with more than one defensible answer come back to you."),
    h("div", { class: "steps" }, names.map((n, i) => h("span", { class: i < session.current ? "done" : i === session.current ? "on" : "" }, n))),
    ...body,
    approved.length ? h("details", { class: "card" }, h("summary", {}, `${approved.length} approved section(s)`), ...approved.map((s) => mdNode(s.markdown))) : null))));
}

function reviewView(session, side) {
  const entry = session.stages[session.current];
  const progress = h("div", { class: "chips" });
  const body = [];
  async function runStage(button) {
    button.disabled = true; progress.replaceChildren();
    try {
      const { job } = await api("POST", `/api/reviews/${session.id}/run`, {});
      await follow(job, { reviewer: (e) => { let c = progress.querySelector(`[data-r="${e.reviewer}"]`);
        if (!c) { c = chip(LENSES[e.reviewer] || e.reviewer); c.dataset.r = e.reviewer; progress.append(c); }
        c.className = `chip ${e.status.replace(/\s+/g, "-")}`; },
        stage: (e) => progress.append(chip(`Stage ${e.number}: ${e.name}`, "on")) });
      route();
    } catch (error) { toast(error.message); button.disabled = false; }
  }
  if (session.state === "complete") {
    body.push(h("div", { class: "card accent" }, h("h4", {}, "Review complete"),
      h("a", { class: "btn primary", href: `#/studio/new:${session.feature}` }, "Specify it in the studio →")));
    if (session.consolidated) body.push(h("div", { class: "card" }, mdNode(session.consolidated)));
  } else if (entry && session.state === "ready") {
    body.push(h("div", { class: "card" }, h("h4", {}, `Stage ${entry.number}: ${entry.name}`),
      h("button", { class: "btn primary", onclick: (e) => runStage(e.target) }, session.preset === "consolidated" ? "Run every stage" : `Run stage ${entry.number}`),
      h("div", { style: "margin-top:12px" }, progress)));
  }
  if (session.state === "paused") body.push(h("div", { class: "card warn" }, h("h4", {}, "Paused"),
    h("p", {}, "Edit the feature document, then re-run this stage or proceed."),
    h("div", { class: "row" }, h("button", { class: "btn", onclick: () => gate("rerun") }, "Re-run this stage"),
      h("button", { class: "btn", onclick: () => gate("proceed") }, "Proceed"))));
  if (entry && entry.report && session.state !== "complete") {
    body.push(h("div", { class: "card" }, mdNode(entry.report)));
  }
  if (entry && entry.report && session.state === "gate") {
    body.push(h("div", { class: "card" }, h("div", { class: "row" },
      h("button", { class: "btn primary", onclick: () => gate("proceed") }, session.current + 1 < session.stages.length ? "Proceed to the next stage" : "Conclude the review"),
      entry.findings && entry.findings.length ? h("button", { class: "btn", onclick: (e) => resolve(e.target) }, "Resolve findings with the Elephant") : null,
      h("button", { class: "btn", onclick: () => gate("rerun") }, "I updated the document: re-run"),
      h("button", { class: "btn ghost", onclick: () => gate("pause") }, "Pause"))));
    if (entry.resolution) body.push(resolutionTable(session, entry));
  }
  async function gate(action) { try { await api("POST", `/api/reviews/${session.id}/gate`, { action }); route(); } catch (e) { toast(e.message); } }
  async function resolve(button) {
    button.disabled = true;
    try { const { job } = await api("POST", `/api/reviews/${session.id}/resolve`, { stage: entry.number }); await follow(job); route(); }
    catch (e) { toast(e.message); button.disabled = false; }
  }
  main().replaceChildren(h("div", { class: "layout" }, side, h("section", { class: "pane" }, h("div", { class: "narrow" },
    h("div", { class: "row" }, h("h1", { class: "grow" }, session.title), chip(session.preset, "on")),
    h("p", { class: "lead" }, "Fresh Goldfish reviewers read only the document. Each stage ends at a gate: proceed, resolve, re-run once after your edits, or pause."),
    h("div", { class: "steps" }, session.stages.map((s, i) => h("span", { class: s.status === "done" || s.status === "skipped" ? "done" : i === session.current ? "on" : "" }, `${s.number}. ${s.name}`))),
    ...body))));
}

function resolutionTable(session, entry) {
  const boxes = [];
  const rows = entry.resolution.map((item) => {
    const box = h("input", { type: "checkbox", checked: item.applicable ? true : null, disabled: item.applicable ? null : true });
    boxes.push([item.index, box]);
    return h("div", { class: "card" },
      h("div", { class: "row" }, box, chip(item.category, item.category === "PROPOSE FIX" ? "on" : item.category === "ESCALATE" ? "unknown" : ""),
        chip(item.finding.severity, item.finding.severity === "Blocker" ? "fail" : item.finding.severity === "Major" ? "unknown" : ""),
        h("strong", { class: "grow" }, item.finding.title)),
      h("p", { class: "small" }, item.justification),
      item.find ? h("details", {}, h("summary", { class: "small" }, item.applicable ? "Proposed edit" : "Proposed edit (text not found exactly once: apply it by hand)"),
        h("pre", { class: "small" }, `- ${item.find}\n+ ${item.replace}`)) : null);
  });
  return h("div", {}, h("h2", {}, "Resolution"), ...rows,
    h("button", { class: "btn primary", onclick: async () => {
      const accepted = boxes.filter(([, b]) => b.checked).map(([i]) => i);
      const result = await api("POST", `/api/reviews/${session.id}/apply`, { stage: entry.number, accepted });
      toast(`${result.applied.length} edit(s) applied${result.refused.length ? `, ${result.refused.length} refused` : ""}.`); route();
    } }, "Apply the accepted fixes"));
}

// ---------- Section 2: spec studio ----------
async function studio(id) {
  const [{ features }, { studio: sessions }] = await Promise.all([api("GET", "/api/features"), api("GET", "/api/studio")]);
  const fileInput = h("input", { type: "file", accept: ".md,.markdown,text/markdown", class: "hidden" });
  const drop = h("div", { class: "drop", tabindex: 0, role: "button", onclick: () => fileInput.click() }, "Drop a feature .md here, or click to choose");
  async function importFile(file) {
    if (!file) return;
    const text = await file.text();
    try { const meta = await api("POST", "/api/features", { markdown: text, title: null }); toast(`Imported: ${meta.title}`); location.hash = `#/studio/new:${meta.id}`; }
    catch (error) { toast(error.message); }
  }
  fileInput.addEventListener("change", () => importFile(fileInput.files[0]));
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); importFile(e.dataTransfer.files[0]); });
  const side = h("aside", { class: "side" }, h("h3", {}, "Import"), drop, fileInput,
    h("h3", {}, "Specifications"), sessions.length ? sessions.map((s) => h("a", { class: `item ${s.id === id ? "on" : ""}`, href: `#/studio/${s.id}` }, s.title, h("small", {}, s.state))) : h("p", { class: "muted small" }, "None yet."),
    h("h3", {}, "Feature documents"), features.map((f) => h("a", { class: "item", href: `#/studio/new:${f.id}` }, f.title, h("small", {}, `${f.kind} · specify →`))));
  if (!id) return main().replaceChildren(h("div", { class: "layout" }, side, h("section", { class: "pane" }, h("div", { class: "narrow empty" },
    h("h1", {}, "Spec studio"), h("p", { class: "lead" }, "Pick a feature document, or drop one. The analyst drafts AxiomSpec obligations; the template's gates check them; you answer what only you can decide; the result is the feature file aeion-observability builds.")))));
  if (id.startsWith("new:")) return main().replaceChildren(h("div", { class: "layout" }, side, await studioNew(id.slice(4))));
  const { session, preview_html } = await api("GET", `/api/studio/${id}`);
  main().replaceChildren(h("div", { class: "layout three" }, side, studioCenter(session), studioPreview(session, preview_html)));
}

async function studioNew(feature) {
  const { meta } = await api("GET", `/api/features/${feature}`);
  const product = h("input", { type: "text", value: "aeion-autonomous-forum" });
  const phase = h("div", { class: "chips" });
  const start = h("button", { class: "btn primary", onclick: async () => {
    start.disabled = true; phase.replaceChildren(chip("Drafting the obligations…", "running"));
    try {
      const { session, job } = await api("POST", "/api/studio", { feature, product: product.value });
      await follow(job, agentProgress((text) => phase.replaceChildren(chip(text, "running"))));
      location.hash = `#/studio/${session.id}`;
    } catch (error) { toast(error.message); start.disabled = false; phase.replaceChildren(); }
  } }, "Draft the specification");
  return h("section", { class: "pane" }, h("div", { class: "narrow" }, h("h1", {}, `Specify: ${meta.title}`),
    h("p", { class: "lead" }, "The analyst turns the document into one goal with its requirements, tests, terms, decisions and assumptions, in the product's canonical knowledge/spec/spec.json."),
    h("div", { class: "card" }, h("label", {}, "Product (its AxiomSpec workspace)"), product,
      h("div", { class: "row", style: "margin-top:16px" }, start, phase))));
}

function studioCenter(session) {
  const checks = session.checks || { gates: {}, export: [], diagnostics: [] };
  const states = ["new", "interview", "ready", "exported"];
  const questions = session.questions || [];
  const discussion = h("div", {}, thread(session.messages || []));
  const body = [
    h("div", { class: "row" }, h("h1", { class: "grow" }, session.title), chip(session.state, session.state === "exported" ? "done" : "on")),
    h("p", { class: "lead" }, `${session.product} · ${session.goal || "no goal yet"} · ${session.nodes.length} records`),
    h("div", { class: "steps" }, ["Draft", "Interview", "Ready", "Exported"].map((n, i) => h("span", { class: states.indexOf(session.state) > i ? "done" : states.indexOf(session.state) === i ? "on" : "" }, n))),
    h("div", { class: "chips" }, ...Object.entries(checks.gates || {}).map(([g, s]) => chip(`${g} ${s}`, s)),
      chip(`Export ${checks.export && checks.export.length ? checks.export.length + " issue(s)" : "ok"}`, checks.export && checks.export.length ? "fail" : "pass")),
  ];
  if (questions.length) body.push(questionCard(session, questions[0], questions.length));
  else if (session.state === "ready") body.push(h("div", { class: "card accent" }, h("h4", {}, "Everything checks"), h("p", {}, "Design gates pass for this feature and the export follows the build factory's rules. Review the preview, then approve.")));
  body.push(entryCard(session), h("h2", {}, "Discuss with the analyst"), discussion,
    composer("Ask why, push back, or describe a change…", async (text) => {
      discussion.querySelector(".thread").append(h("div", { class: "msg user" }, text));
      const bubble = streamingBubble(discussion.querySelector(".thread"));
      const { job } = await api("POST", `/api/studio/${session.id}/discuss`, { text });
      await follow(job, bubble.handlers()); bubble.done(); route();
    }),
    h("button", { class: "btn", style: "margin-top:8px", onclick: async (e) => { e.target.disabled = true;
      try { const { job } = await api("POST", `/api/studio/${session.id}/change`, { instruction: "" });
        await follow(job, agentProgress((text) => { e.target.textContent = text; })); route(); }
      catch (x) { toast(x.message); e.target.disabled = false; e.target.textContent = "Apply what we agreed as a change"; } } }, "Apply what we agreed as a change"));
  return h("section", { class: "pane" }, h("div", { class: "narrow" }, ...body));
}

function questionCard(session, question, total) {
  const text = h("textarea", { rows: 3, placeholder: question.free_text ? "Your answer, in your words (optional when you pick an option)" : "" });
  let choice = null;
  const options = h("div", { class: "row" }, ...(question.options || []).map((o) => h("button", { class: "btn small", onclick: (e) => {
    choice = o; options.querySelectorAll("button").forEach((b) => b.classList.remove("primary")); e.target.classList.add("primary"); } }, o)));
  const working = h("span", { class: "muted small" });
  const send = h("button", { class: "btn primary", onclick: async () => {
    send.disabled = true; working.textContent = "Checking…";
    try {
      const { job } = await api("POST", `/api/studio/${session.id}/answer`, { question: question.id, choice, text: text.value });
      await follow(job, agentProgress((text) => { working.textContent = text; }));
      route();
    } catch (error) { toast(error.message); send.disabled = false; working.textContent = ""; }
  } }, "Answer");
  return h("div", { class: `card ${question.required ? "warn" : ""}` },
    h("div", { class: "row" }, h("span", { class: "muted small grow" }, `Question 1 of ${total} · ${question.kind}${question.subject ? " · " + question.subject : ""}`), question.required ? chip("required", "unknown") : chip("optional")),
    h("h4", { style: "margin-top:6px" }, question.title), question.detail ? mdNode(question.detail, "muted small") : null,
    options, question.free_text ? h("div", { style: "margin-top:10px" }, text) : null, h("div", { class: "row", style: "margin-top:10px" }, send, working));
}

function entryCard(session) {
  const entry = session.entry || {};
  const target = refreshStatus.target || {};
  const select = (values, value) => h("select", {}, h("option", { value: "" }, "—"), ...(values || []).map((v) => h("option", { value: v, selected: v === value ? true : null }, v)));
  const fields = {
    title: h("input", { type: "text", value: entry.title || "" }),
    area: select(target.areas, entry.area), phase: select(target.phases, entry.phase), size: select(["S", "M", "L"], entry.size),
    write_paths: h("textarea", { rows: 3 }, (entry.write_paths || []).join("\n")),
    depends_on: h("input", { type: "text", value: (entry.depends_on || []).join(", "), placeholder: "e.g. 004, 021" }),
    delivery: h("textarea", { rows: 4 }, (entry.delivery || []).join("\n")),
    out_of_scope: h("textarea", { rows: 3 }, (entry.out_of_scope || []).join("\n")),
  };
  const save = h("button", { class: "btn", onclick: async () => {
    const values = Object.fromEntries(Object.entries(fields).map(([k, el]) => [k, el.value]));
    try { await api("POST", `/api/studio/${session.id}/entry`, { fields: values }); toast("Export settings saved and checked."); route(); } catch (e) { toast(e.message); }
  } }, "Save and check");
  return h("details", { class: "card", open: session.checks && session.checks.export && session.checks.export.length ? true : null },
    h("summary", {}, h("strong", {}, "Export settings for aeion-observability")),
    h("label", {}, "Title"), fields.title,
    h("div", { class: "row" }, h("div", { class: "grow" }, h("label", {}, "Area"), fields.area), h("div", { class: "grow" }, h("label", {}, "Phase"), fields.phase), h("div", { class: "grow" }, h("label", {}, "Size"), fields.size)),
    h("label", {}, "Write paths (one per line)"), fields.write_paths,
    h("label", {}, "Depends on (catalog IDs)"), fields.depends_on,
    h("label", {}, "Delivery steps (one per line, 2-4, at most 220 characters)"), fields.delivery,
    h("label", {}, "Out of scope (one per line)"), fields.out_of_scope,
    h("div", { class: "row", style: "margin-top:12px" }, save));
}

function studioPreview(session, previewHtml) {
  const checks = session.checks || {};
  const bytes = checks.bytes || 0;
  const markdownText = checks.preview || "";
  const percent = Math.min(100, Math.round((bytes / 12000) * 100));
  const approve = h("button", { class: "btn primary", disabled: session.state === "ready" ? null : true, onclick: async () => {
    approve.disabled = true;
    try { const { job } = await api("POST", `/api/studio/${session.id}/approve`, {}); await follow(job, { phase: (e) => toast(e.phase) }); toast("Approved and exported."); route(); }
    catch (error) { toast(error.message); approve.disabled = false; }
  } }, "Approve and export");
  const exported = session.export;
  return h("aside", { class: "pane split" },
    h("div", { class: "row" }, h("h2", { class: "grow", style: "margin:0" }, "Feature file"), approve),
    h("div", { class: "meter" }, h("i", { class: percent > 85 ? "high" : "", style: `width:${percent}%` })),
    h("p", { class: "muted small" }, `${bytes.toLocaleString()} of 12,000 bytes · eight sections · frontmatter for the build factory's catalog`),
    exported ? h("div", { class: "card accent" }, h("h4", {}, `Exported as ${exported.file}`),
      h("p", { class: "small" }, "Give this file to aeion-observability (demo/forum/features/) and add the row to its MANIFEST.json. aeion-core never writes there."),
      h("div", { class: "row" }, h("button", { class: "btn small", onclick: () => download(exported.file, markdownText) }, "Download .md"),
        h("button", { class: "btn small", onclick: () => download(exported.file.replace(/\.md$/, ".manifest-row.json"), JSON.stringify(exported.row, null, 2) + "\n", "application/json") }, "Download manifest row"),
        h("a", { class: "btn small", href: `#/docs/product/${session.product}:docs/README.md` }, "Open the product docs"))) : null,
    previewHtml ? h("div", { class: "doc", html: previewHtml }) : h("p", { class: "muted" }, "The preview appears once the specification validates."));
}

// ---------- Section 3: documentation ----------
let docsTree = null;
const askHistory = [];
async function docs(id) {
  docsTree = (await api("GET", "/api/docs/tree")).tree;
  const search = h("input", { type: "text", placeholder: "Search the documentation…" });
  const list = h("div", {});
  const showTree = () => list.replaceChildren(...docsTree.map((group) => h("details", { open: group.root.startsWith("product/") || group.root === "features" ? true : null },
    h("summary", { class: "item" }, h("strong", {}, group.title), h("small", {}, `${group.pages.length} page${group.pages.length === 1 ? "" : "s"}`)),
    ...group.pages.map((p) => h("a", { class: `item ${p.id === id.split("::")[0] ? "on" : ""}`, href: `#/docs/${p.id}`, style: "padding-left:20px" }, p.title, h("small", {}, p.path))))));
  showTree();
  let timer;
  search.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(async () => {
    if (!search.value.trim()) return showTree();
    const { results } = await api("GET", `/api/docs/search?q=${encodeURIComponent(search.value)}`);
    list.replaceChildren(...results.map((r) => h("a", { class: "item", href: `#/docs/${r.page}${r.anchor ? "::" + r.anchor : ""}` }, r.section, h("small", {}, r.snippet))));
  }, 180); });
  const side = h("aside", { class: "side" }, search, h("div", { style: "margin-top:10px" }, list));
  const [pageId, anchor] = id.split("::");
  const center = h("section", { class: "pane" });
  if (pageId) {
    try {
      const page = await api("GET", `/api/docs/page?id=${encodeURIComponent(pageId)}`);
      center.append(h("div", { class: "narrow" }, h("p", { class: "muted small" }, `${page.group} › ${page.path}`),
        page.diagrams.length ? h("div", { class: "diagrams" }, ...page.diagrams.map((d) => h("figure", { class: "diagram" },
          h("img", { src: d.src, alt: d.title, loading: "lazy" }), h("figcaption", {}, `${d.title} · ${d.claim} · ${d.question}`)))) : null,
        h("article", { class: "doc", html: page.html })));
    } catch (error) { center.append(h("div", { class: "empty" }, h("h1", {}, "Page not found"), h("p", {}, error.message))); }
  } else {
    center.append(h("div", { class: "narrow empty" }, h("h1", {}, "Documentation"),
      h("p", { class: "lead" }, "Products, feature documents, the AxiomSpec and Elephant-Goldfish methods, and aeion-core itself. Ask the assistant on the right: it searches the pages and the AxiomSpec graph, and cites what it uses.")));
  }
  main().replaceChildren(h("div", { class: "layout three" }, side, center, askPanel()));
  if (anchor) setTimeout(() => document.getElementById(anchor)?.scrollIntoView({ block: "start" }), 50);
}

function askPanel() {
  const log = h("div", { class: "thread" }, ...askHistory.map((m) => h("div", { class: `msg ${m.role}` }, m.role === "user" ? m.content : mdNode(m.content, ""))));
  return h("aside", { class: "pane split" }, h("h2", { style: "margin-top:0" }, "Ask the docs"),
    h("p", { class: "muted small" }, "Answers come from the documents and the knowledge graph, with numbered sources."), log,
    composer("What verifies REQ-004? How does a review stage work?", async (question) => {
      log.append(h("div", { class: "msg user" }, question));
      const tools = h("div", {}); log.append(tools);
      const bubble = streamingBubble(log);
      const { job } = await api("POST", "/api/docs/ask", { question, history: askHistory.slice(-6), conversation: "panel" });
      const result = await follow(job, { ...bubble.handlers(),
        tool: (e) => tools.append(h("div", { class: "tool" }, `${e.action === "search" ? "🔎" : e.action === "open" ? "📄" : e.action === "graph" ? "🕸" : "·"} ${e.action} ${e.detail || ""}`)) });
      bubble.done();
      log.append(h("div", { class: "sources" }, ...result.sources.map((s) => s.page
        ? h("a", { class: "chip on", href: `#/docs/${s.page}${s.anchor ? "::" + s.anchor : ""}` }, `[${s.number}] ${s.title}`)
        : chip(`[${s.number}] ${s.title}`))));
      askHistory.push({ role: "user", content: question }, { role: "assistant", content: result.answer });
    }));
}

// ---------- start ----------
window.addEventListener("hashchange", () => route().catch((e) => toast(e.message)));
window.addEventListener("DOMContentLoaded", async () => {
  await refreshStatus();
  try { refreshStatus.target = (await api("GET", "/api/catalog")).target; } catch (e) { refreshStatus.target = {}; }
  setInterval(refreshStatus, 6000);
  route().catch((e) => toast(e.message));
});
