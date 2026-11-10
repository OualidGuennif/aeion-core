'use agent';
// Spec: knowledge/components/aeion-agents.md
// The EGM synthesizer in brainstorm mode: the anchored hypothesis and the seven Goldfish reports become the
// concepts brief, written as the reply.
import { useModel, useSkill } from '@flue/runtime';
import { DATA_RULE, setup, useBlocks } from '../common.ts';
import synthesis from '../skills/egm-synthesis/SKILL.md';

const { model, input } = setup();

export function Synthesizer() {
  useModel(model, { compaction: false, thinkingLevel: 'max' });
  useBlocks(input);
  useSkill(synthesis);
  return [
    'You are the synthesizer of the Elephant-Goldfish Model, in brainstorm mode. Activate the `egm-synthesis` skill',
    'first and follow its brainstorm procedure. The anchored hypothesis, the conversation notes and the Goldfish',
    'reports are attached. Your whole answer is the concepts brief in Markdown, nothing before or after it.',
    DATA_RULE,
  ].join('\n');
}
