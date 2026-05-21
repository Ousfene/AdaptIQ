/**
 * src/services/adminService.ts
 *
 * Thin admin API client for dashboard cards and concept analytics.
 */

import { API_BASE } from '../config';

// Build admin request headers with optional bearer token.
function authHeaders() {
  const token = localStorage.getItem('adaptiq_token');
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export interface AdminOverview {
  users: { total: number; active: number; admin?: number; latest_created_at: string | null };
  questions: { total: number; llm_generated?: number; cached?: number; latest_created_at: string | null };
  sessions: { classic?: number; challenge: number; custom: number; pvp?: number };
  concepts: { total: number; mastery_rows: number };
  responses: { total: number };
  pvp?: { total_matches: number; rated_players: number };
}

export interface AdminConceptStat {
  concept_id: string;
  name: string;
  topic: string;
  tracked_users: number;
  avg_theta: number;
}

// Fetch high-level admin overview counters.
export async function fetchAdminOverview(): Promise<AdminOverview> {
  const res = await fetch(`${API_BASE}/api/admin/overview`, {
    headers: authHeaders(),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail ?? `HTTP ${res.status}`);
  }
  return data as AdminOverview;
}

// Fetch top concepts ordered by tracked-user activity.
export async function fetchTopConcepts(limit = 10): Promise<AdminConceptStat[]> {
  const res = await fetch(`${API_BASE}/api/admin/top-concepts?limit=${limit}`, {
    headers: authHeaders(),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail ?? `HTTP ${res.status}`);
  }
  return (data.items ?? []) as AdminConceptStat[];
}
