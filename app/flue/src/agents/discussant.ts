'use agent';
// Spec: knowledge/components/aeion-agents.md
// Talks a feature's specification through with the owner. It reads and checks, never writes: a change happens
// only when the owner asks the studio to apply it.
import { useModel, useSkill, useTool } from '@flue/runtime';
import { DATA_RULE, setup, useBlocks } from '../common.ts';
import { readRecord, runChecks } from '../tools/records.ts';
import authoring from '../skills/axiomspec-authoring/SKILL.md';

const { model, input } = setup();

export function Discussant() {
  useModel(model, { compaction: false, thinkingLevel: 'max' });
  useBlocks(input);
  useSkill(authoring);
  useTool(readRecord);
  useTool(runChecks);
  return [
    'You are the requirements analyst discussing a feature\'s AxiomSpec specification with its owner. Activate the',
    '`axiomspec-authoring` skill when the discussion touches how a record must be written. The feature\'s records,',
    'the open checks and the earlier discussion are attached; the owner\'s new message is this turn\'s message.',
    'Stress-test: say what is wrong or risky first. Keep it short and ask at most one question. You cannot change',
    'anything: say which change you would make, and the owner applies it with "Apply as a change".',
    DATA_RULE,
  ].join('\n');
}
