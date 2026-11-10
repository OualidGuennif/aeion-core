'use agent';
// Spec: knowledge/components/aeion-agents.md
// Compares a finished design draft with the brief it came from; reports contradictions, changes nothing.
import { useModel, useSkill, useTool } from '@flue/runtime';
import { DATA_RULE, setup, submitTool, useBlocks, useRequiredSubmission } from '../common.ts';
import draft from '../skills/egm-draft/SKILL.md';

const { model, input } = setup();
const submit = submitTool('submit_reconciliation', 'Submit the contradictions and the architecture-changing additions.', input);

export function Reconciler() {
  useModel(model, { compaction: false, thinkingLevel: 'max' });
  useBlocks(input);
  useSkill(draft);
  useTool(submit);
  useRequiredSubmission('submit_reconciliation');
  return [
    'You compare a finished design draft with the brief it came from. Activate the `egm-draft` skill first and follow',
    'its reconciliation procedure. The brief and the draft are attached. Quote both sides exactly; change nothing.',
    'Submit with `submit_reconciliation` once, then stop.',
    DATA_RULE,
  ].join('\n');
}
