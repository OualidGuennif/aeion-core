// Spec: knowledge/components/aeion-agents.md
// Every `flue run` is one disposable conversation: the Python server keeps the durable record (sessions,
// specifications), so Flue's own store stays in memory. Parallel runs never share or grow a database file.
import { sqlite } from '@flue/runtime/node';

export default sqlite(':memory:');
