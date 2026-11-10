'use agent';
// Spec: knowledge/components/aeion-agents.md
// The Elephant resolving one review stage's findings (egm-resolve); the server checks every proposed edit applies once.
import { useModel, useSkill, useTool } from '@flue/runtime';
import { DATA_RULE, setup, submitTool, useBlocks, useRequiredSubmission } from '../common.ts';
import resolve from '../skills/egm-resolve/SKILL.md';

const { model, input } = setup();
const submit = submitTool('submit_resolution', 'Submit one categorized item per finding, with exact edits for PROPOSE FIX.', input);

export function Resolver() {
  useModel(model, { compaction: false, thinkingLevel: 'max' });
  useBlocks(input);
  useSkill(resolve);
  useTool(submit);
  useRequiredSubmission('submit_resolution');
  return [
    'You are the Elephant resolving Goldfish findings on a document you helped write. Activate the `egm-resolve`',
    'skill first and follow it. The document and its numbered findings are attached. Submit the resolution with',
    '`submit_resolution` once it covers every finding, then stop.',
    DATA_RULE,
  ].join('\n');
}
