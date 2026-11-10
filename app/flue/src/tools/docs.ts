// Spec: knowledge/components/aeion-agents.md
// The documentation tools: ranked search, one page or section, and a node of an AxiomSpec knowledge graph.
// Every result carries evidence numbers [n] that the answer cites.
import * as v from 'valibot';
import { bridgeTool } from '../common.ts';

export const searchDocs = bridgeTool('search_docs',
  'Search every documentation page (products, feature documents, AxiomSpec, the Elephant-Goldfish Model, aeion-core). '
  + 'Returns ranked sections with their page id, section anchor, a snippet and an evidence number [n].',
  v.strictObject({ query: v.pipe(v.string(), v.minLength(2), v.maxLength(200)) }));

export const openPage = bridgeTool('open_page',
  'Open one page by the page id a search returned. Give `section` (an anchor from a search result or from the page '
  + 'outline) to read one section of a long page; without it a long page returns its outline. Returns text with an '
  + 'evidence number [n].',
  v.strictObject({ page: v.pipe(v.string(), v.maxLength(300)), section: v.optional(v.pipe(v.string(), v.maxLength(200))) }));

export const graphQuery = bridgeTool('graph_query',
  'Query an AxiomSpec knowledge graph for one node and its typed links: what verifies, implements, depends on or '
  + 'governs it, and which files and tests cover it. `id` is a canonical ID (REQ-004, DEC-001) or a file path; '
  + '`product` is a product name, or "core" for aeion-core itself. Returns text with an evidence number [n].',
  v.strictObject({ id: v.pipe(v.string(), v.minLength(2), v.maxLength(300)),
                   product: v.optional(v.pipe(v.string(), v.maxLength(100))) }));
