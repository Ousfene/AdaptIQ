/**
 * src/services/http.ts
 *
 * Shared request-header helper for authenticated frontend API calls.
 */

// Compose auth headers, optionally including JSON content type.
export function authHeaders(contentType = true): Record<string, string> {
  const token = localStorage.getItem('adaptiq_token');
  return {
    ...(contentType ? { 'Content-Type': 'application/json' } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}
