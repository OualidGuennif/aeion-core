'use agent';
// Spec: knowledge/components/aeion-agents.md
// The Elephant drafting one section of a design document, or asking the owner the architectural question
// that section depends on.
import { useModel, useSkill, useTool } from '@flue/runtime';
import { DATA_RULE, setup, useBlocks } from '../common.ts';
import { askOwner } from '../tools/conversation.ts';
import draft from '../skills/egm-draft/SKILL.md';

const { model, input } = setup();

export function Drafter() {
  useModel(model, { compaction: false, thinkingLevel: 'max' });
  useBlocks(input);
  useSkill(draft);
  useTool(askOwner);
  return [
    'You are the Elephant drafting a design document with its owner, one section at a time. Activate the `egm-draft`',
    'skill first and follow it. The predecessor material, the approved sections and, when redrafting, the current',
    'draft of this section are attached; the message names the section and carries the owner\'s instruction or answer.',
    'Your whole answer is the section in Markdown, unless the choice is the owner\'s: then call `ask_owner` instead.',
    DATA_RULE,
  ].join('\n');
}
