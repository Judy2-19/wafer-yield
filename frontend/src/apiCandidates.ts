export function buildApiCandidates(configuredBase?: string): string[] {
  return [
    configuredBase,
    '/api',
    'http://127.0.0.1:8000/api',
    'http://localhost:8000/api',
  ].filter((value): value is string => !!value && value.trim().length > 0)
}
