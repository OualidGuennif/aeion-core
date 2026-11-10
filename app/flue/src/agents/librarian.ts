'use agent';
// Spec: knowledge/components/aeion-agents.md
// The documentation assistant: agentic retrieval over the pages and the AxiomSpec knowledge graphs, then a
// cited answer. Every tool result carries evidence numbers; the answer cites only those.
import { useModel, useSkill, useTool } from '@flue/runtime';
import { DATA_RULE, setup, useBlocks } from '../common.ts';
import { graphQuery, openPage, searchDocs } from '../tools/docs.ts';
import research from '../skills/docs-research/SKILL.md';

const { model, input } = setup();

export function Librarian() {
  useModel(model, { compaction: false, thinkingLevel: 'max' });
  useBlocks(input);
  useSkill(research);
  useTool(searchDocs);
  useTool(openPage);
  useTool(graphQuery);
  return [
    'You answer questions about aeion-core\'s documentation: its products\' AxiomSpec specifications, saved feature',
    'documents, the AxiomSpec and Elephant-Goldfish methods, and aeion-core itself. Activate the `docs-research` skill',
    'first and follow it. The earlier questions and answers, when there are some, are attached as `conversation`; the',
    'question is this turn\'s message. Answer only from what the tools returned, citing [n].',
    DATA_RULE,
  ].join('\n');
}
