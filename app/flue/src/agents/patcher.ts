'use agent';
// Spec: knowledge/components/aeion-agents.md
// Turns the owner's instruction (or a failed check) into a patch of one feature's records; the server applies
// it to a scratch copy, runs the checks and reports what still fails.
import { useModel, useSkill, useTool } from '@flue/runtime';
import { DATA_RULE, setup, submitTool, useBlocks, useRequiredSubmission } from '../common.ts';
import { readRecord } from '../tools/records.ts';
import authoring from '../skills/axiomspec-authoring/SKILL.md';

const { model, input } = setup();
const submit = submitTool('submit_patch', 'Submit one patch of this feature: updates, additions, drops and export fields.', input);

export function Patcher() {
  useModel(model, { compaction: false, thinkingLevel: 'max' });
  useBlocks(input);
  useSkill(authoring);
  useTool(readRecord);
  useTool(submit);
  useRequiredSubmission('submit_patch');
  return [
    'You change one feature of an AxiomSpec specification exactly as the owner asked, or to fix a failed check, with',
    'the smallest correct patch. Activate the `axiomspec-authoring` skill first and follow its Changes section. The',
    'feature\'s records, the recent conversation and the open checks are attached; the message is the instruction.',
    'Read a record with `read_record` when you need its exact fields. Submit with `submit_patch`; the server answers',
    'with what still fails: fix it and submit the complete patch again. Never set a decision\'s answer.',
    DATA_RULE,
  ].join('\n');
}
