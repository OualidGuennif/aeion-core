// Spec: knowledge/components/aeion-agents.md
// The event stream the Python server reads while an agent runs: answer text as it streams (the page
// shows it), the amount of reasoning (never its content), tool activity, usage per model turn and the
// final outcome. Prompts and tool arguments are not copied.
import { closeSync, openSync, writeSync } from 'node:fs';
import { observe } from '@flue/runtime';

const FINISH = new Set(['stop', 'toolUse', 'length', 'error', 'aborted']);
const count = (value: unknown) => (typeof value === 'number' ? value : null);

export function toRecord(event: any): Record<string, unknown> | null {
  switch (event?.type) {
    case 'turn_start':
      return { type: 'turn_start', turn: event.turnId ?? null };
    case 'text_delta':
      return { type: 'text', turn: event.turnId ?? null, text: String(event.text ?? '') };
    case 'thinking_delta':
      return { type: 'thinking', turn: event.turnId ?? null, chars: String(event.delta ?? '').length };
    case 'tool_start':
      return { type: 'tool_start', name: String(event.toolName ?? 'other') };
    case 'tool':
      return { type: 'tool', name: String(event.toolName ?? 'other'), status: event.isError === true ? 'error' : 'completed' };
    case 'turn': {
      const usage = event.response?.usage;
      const finish = event.response?.finishReason;
      return {
        type: 'turn', turn: event.turnId ?? null, error: event.isError === true,
        finish: FINISH.has(finish) ? finish : 'other', durationMs: count(event.durationMs),
        usage: usage ? { input: count(usage.input), output: count(usage.output), cacheRead: count(usage.cacheRead),
                         cost: count(usage.cost?.total) } : null,
      };
    }
    case 'submission_settled':
      return { type: 'settled', outcome: String(event.outcome ?? 'other') };
    default:
      return null;
  }
}

export function observeToFile(path: string | undefined = process.env.AEION_EVENTS_FILE) {
  if (!path) throw new Error('AEION_EVENTS_FILE is required');
  const fd = openSync(path, 'a', 0o600);
  const stop = observe((event) => {
    const record = toRecord(event);
    if (record) writeSync(fd, JSON.stringify(record) + '\n');
  });
  return () => { stop(); closeSync(fd); };
}
