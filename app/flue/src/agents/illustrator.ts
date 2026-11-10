'use agent';
// Spec: knowledge/components/aeion-agents.md
// Proposes the diagrams of an approved feature in aeion-view/0.1; the server renders each one and refuses what
// does not render.
import { useModel, useSkill, useTool } from '@flue/runtime';
import { DATA_RULE, setup, submitTool, useBlocks, useRequiredSubmission } from '../common.ts';
import views from '../skills/aeion-views/SKILL.md';

const { model, input } = setup();
const submit = submitTool('submit_views', 'Submit one to three diagrams of this feature as aeion-view/0.1 sources.', input);

export function Illustrator() {
  useModel(model, { compaction: false, thinkingLevel: 'max' });
  useBlocks(input);
  useSkill(views);
  useTool(submit);
  useRequiredSubmission('submit_views');
  return [
    'You draw the diagrams that help a reader understand one feature. Activate the `aeion-views` skill first and',
    'follow it. The feature\'s records are attached. Submit with `submit_views`; fix whatever the server refuses.',
    DATA_RULE,
  ].join('\n');
}
