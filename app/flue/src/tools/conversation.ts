// Spec: knowledge/components/aeion-agents.md
// Tools that hand a decision back to the owner: the anchored hypothesis and a design question.
import * as v from 'valibot';
import { bridgeTool } from '../common.ts';

export const anchorHypothesis = bridgeTool('anchor_hypothesis',
  'Record the anchored working hypothesis (2-3 sentences: who, what, the binding constraints, the success measure) '
  + 'once the problem, its boundaries and its success measure are clear. The owner then chooses a Goldfish review or '
  + 'more clarification. Call it again to update the hypothesis after a new constraint.',
  v.strictObject({ hypothesis: v.pipe(v.string(), v.minLength(20), v.maxLength(1500)) }));

export const askOwner = bridgeTool('ask_owner',
  'Ask the owner one architectural question instead of writing the section: lay out up to three options, each with '
  + 'its mechanism, trade-offs and failure conditions, unranked and with no default. Ends your turn.',
  v.strictObject({ question: v.pipe(v.string(), v.minLength(20), v.maxLength(4000)) }));
