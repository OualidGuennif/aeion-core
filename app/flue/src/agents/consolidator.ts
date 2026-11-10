'use agent';
// Spec: knowledge/components/aeion-agents.md
// The EGM synthesizer in review mode: one stage's Goldfish reports become deduplicated findings, submitted
// through a typed tool the server validates.
import { useModel, useSkill, useTool } from '@flue/runtime';
import { DATA_RULE, setup, submitTool, useBlocks, useRequiredSubmission } from '../common.ts';
import synthesis from '../skills/egm-synthesis/SKILL.md';

const { model, input } = setup();
const submit = submitTool('submit_findings', 'Submit every finding of this review stage, deduplicated and ranked.', input);

export function Consolidator() {
  useModel(model, { compaction: false, thinkingLevel: 'max' });
  useBlocks(input);
  useSkill(synthesis);
  useTool(submit);
  useRequiredSubmission('submit_findings');
  return [
    'You are the synthesizer of the Elephant-Goldfish Model, in review mode. Activate the `egm-synthesis` skill first',
    'and follow its review procedure. The target and the Goldfish reports of one stage are attached. Submit the',
    'findings with `submit_findings` exactly once when complete (an empty list when no reviewer found anything), then stop.',
    DATA_RULE,
  ].join('\n');
}
