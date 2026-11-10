'use agent';
// Spec: knowledge/components/aeion-agents.md
// The spec studio's requirements analyst: a feature document becomes AxiomSpec obligations. Each submission is
// merged into a scratch copy of the product specification and checked by the template's own gates and the
// build factory's export rules; the analyst fixes what fails before it stops.
import { useModel, useSkill, useTool } from '@flue/runtime';
import { DATA_RULE, setup, submitTool, useBlocks, useRequiredSubmission } from '../common.ts';
import { listCatalog } from '../tools/records.ts';
import authoring from '../skills/axiomspec-authoring/SKILL.md';

const { model, input } = setup();
const submit = submitTool('submit_fragment', 'Submit the feature\'s complete obligations: goal, terms, requirements, '
  + 'decisions, assumptions, tests, components and export fields. Call it once; fix what fails with amend_fragment.', input);
const amend = submitTool('amend_fragment', 'Fix the recorded fragment after submit_fragment reported failing checks: send '
  + 'only what changes. An item with an existing key replaces that item, a new key adds one, `remove` drops keys; '
  + 'title, goal and export replace the whole field when given. Every field is optional.', input);

export function Analyst() {
  useModel(model, { compaction: false, thinkingLevel: 'max' });
  useBlocks(input);
  useSkill(authoring);
  useTool(listCatalog);
  useTool(submit);
  useTool(amend);
  useRequiredSubmission('submit_fragment');
  return [
    'You are the requirements analyst of aeion-core. You turn a feature document into AxiomSpec obligations that a',
    'build factory can implement and verify without asking anyone. Activate the `axiomspec-authoring` skill first and',
    'follow it. The feature document and the build factory\'s allowed export values are attached. Use `list_catalog`',
    'once, without a query, to pick real dependencies. Submit the complete fragment once with `submit_fragment`; the',
    'server answers with the deterministic checks that fail: fix them with `amend_fragment`, sending only the items that',
    'change. Never answer a decision: the owner does.',
    DATA_RULE,
  ].join('\n');
}
