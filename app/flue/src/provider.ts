// Spec: knowledge/components/aeion-agents.md
// The model every aeion-core agent uses: OpenCode Go's deepseek-v4.1-flash, reached only through the
// Python server's loopback relay. The relay token authenticates to the relay; the OpenCode key never
// reaches this process. Reasoning runs at the model's native maximum by default.
import { createProvider } from '@earendil-works/pi-ai';
import { openAICompletionsApi } from '@earendil-works/pi-ai/api/openai-completions.lazy';
import { setProvider } from '@flue/runtime';

export const PROVIDER_ID = 'opencode-go';

type ModelMetadata = {
  id: string;
  name: string;
  context: number;
  input: number;
  output: number;
  cacheRead: number;
  maxOutputTokens: number;
};

// Native effort names per model; aeion-core agents ask for 'max'.
const THINKING: Record<string, Record<string, string>> = {
  'deepseek-v4.1-flash': { minimal: 'low', low: 'low', medium: 'high', high: 'high', xhigh: 'max', max: 'max' },
};

export function modelFromEnv(env: NodeJS.ProcessEnv = process.env) {
  // Steps: the loopback relay only; the model metadata the server chose; a bounded output budget.
  const relayUrl = env.AEION_RELAY_URL;
  if (!relayUrl || !/^http:\/\/127\.0\.0\.1:\d+\/v1$/.test(relayUrl)) throw new Error('AEION_RELAY_URL must be the loopback relay');
  if (!env.AEION_RELAY_TOKEN) throw new Error('AEION_RELAY_TOKEN is required');
  const meta: ModelMetadata = JSON.parse(env.AEION_MODEL_JSON ?? 'null');
  if (!meta || typeof meta.id !== 'string' || !Number.isSafeInteger(meta.context)) throw new Error('AEION_MODEL_JSON is invalid');
  if (!Number.isSafeInteger(meta.maxOutputTokens) || meta.maxOutputTokens < 1 || meta.maxOutputTokens > 65536) {
    throw new Error('Output budget invalid');
  }
  return {
    id: meta.id,
    name: meta.name,
    api: 'openai-completions' as const,
    provider: PROVIDER_ID,
    baseUrl: relayUrl,
    reasoning: true,
    input: ['text' as const],
    cost: { input: meta.input, output: meta.output, cacheRead: meta.cacheRead, cacheWrite: 0 },
    contextWindow: meta.context,
    maxTokens: meta.maxOutputTokens,
    thinkingLevelMap: THINKING[meta.id] ?? {},
    compat: {
      supportsDeveloperRole: false,
      supportsStore: false,
      supportsReasoningEffort: meta.id in THINKING,
      // DeepSeek: thinking {type: enabled} plus reasoning_effort; reasoning is replayed as reasoning_content.
      ...(meta.id.startsWith('deepseek') ? { thinkingFormat: 'deepseek' as const } : {}),
      supportsUsageInStreaming: true,
      maxTokensField: 'max_tokens' as const,
    },
  };
}

export function registerProvider(env: NodeJS.ProcessEnv = process.env) {
  const model = modelFromEnv(env);
  const token = env.AEION_RELAY_TOKEN;
  setProvider(createProvider({
    id: PROVIDER_ID,
    name: 'OpenCode Go via the aeion-core relay',
    baseUrl: model.baseUrl,
    auth: { apiKey: { name: 'aeion-core relay token', resolve: async () => ({ auth: { apiKey: token } }) } },
    models: [model],
    api: openAICompletionsApi(),
  }));
  return `${PROVIDER_ID}/${model.id}`;
}
