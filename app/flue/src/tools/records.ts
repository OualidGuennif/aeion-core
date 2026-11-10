// Spec: knowledge/components/aeion-agents.md
// Read-only views of a product's specification and of the build factory's catalog, served by the server.
import * as v from 'valibot';
import { bridgeTool } from '../common.ts';

export const readRecord = bridgeTool('read_record',
  'Read one record of the product specification by its ID (REQ-001, TEST-004, DEC-001, TERM-002...): its fields, '
  + 'status and typed links. Use it before changing or discussing a record.',
  v.strictObject({ id: v.pipe(v.string(), v.regex(/^[A-Z]+-[0-9A-Z-]{1,40}$/)) }));

export const runChecks = bridgeTool('run_checks',
  'Run the deterministic checks on this feature as it stands now (design gates G01-G07, the build factory\'s export '
  + 'rules and the exported size). Read-only.',
  v.strictObject({}));

export const listCatalog = bridgeTool('list_catalog',
  'List features already in the build factory\'s catalog (id, title, phase, area), optionally filtered by words, to '
  + 'choose real dependencies and avoid duplicating an existing feature. Call it once without a query to get the whole '
  + 'catalog (at most three calls per run). Read-only.',
  v.strictObject({ query: v.optional(v.pipe(v.string(), v.maxLength(120))) }));
