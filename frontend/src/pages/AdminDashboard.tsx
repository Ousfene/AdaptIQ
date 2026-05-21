/**
 * pages/AdminDashboard.tsx — Admin dashboard with overview stats, user/question/session lists.
 *
 * Features:
 *   - Overview cards (users, questions, sessions, PvP)
 *   - User list with search + toggle active/admin
 *   - Question list with topic filter
 *   - Session list (challenge + custom)
 *   - Concept mastery overview
 *   - Monitoring stats
 *
 * Requires admin privileges (is_admin = true).
 */

import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import InternalLayout from '../components/InternalLayout';
import { API_BASE } from '../config';
import { authHeaders } from '../services/http';

interface OverviewData {
  users: { total: number; active: number; latest_created_at: string | null };
  questions: { total: number; latest_created_at: string | null };
  sessions: { challenge: number; custom: number; pvp: number };
  concepts: { total: number; mastery_rows: number };
  responses: { total: number };
  pvp: { total_matches: number; rated_players: number };
}

interface InspectorColumn {
  name: string;
  type: string;
  nullable: boolean;
  primary_key: boolean;
}

interface InspectorTable {
  name: string;
  row_count: number;
  columns: InspectorColumn[];
}

// GET helper for admin dashboard endpoints.
async function adminFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// PATCH helper for admin mutation endpoints.
async function adminPatch(path: string): Promise<any> {
  const res = await fetch(`${API_BASE}${path}`, { method: 'PATCH', headers: authHeaders() });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

type Tab = 'overview' | 'users' | 'questions' | 'sessions' | 'concepts' | 'governance' | 'inspector' | 'monitoring';

// Render admin dashboard tabs, tables, and refresh actions.
export default function AdminDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('overview');

  // Overview
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [topConcepts, setTopConcepts] = useState<any[]>([]);

  // Users
  const [users, setUsers] = useState<any[]>([]);
  const [usersTotal, setUsersTotal] = useState(0);
  const [userSearch, setUserSearch] = useState('');
  const [userPage, setUserPage] = useState(1);

  // Questions
  const [questions, setQuestions] = useState<any[]>([]);
  const [qTotal, setQTotal] = useState(0);
  const [qTopic, setQTopic] = useState('');
  const [qPage, setQPage] = useState(1);

  // Sessions
  const [sessions, setSessions] = useState<any[]>([]);

  // Concepts
  const [concepts, setConcepts] = useState<any[]>([]);
  const [conceptsTotal, setConceptsTotal] = useState(0);
  const [conceptTopic, setConceptTopic] = useState('');
  const [conceptPage, setConceptPage] = useState(1);
  const [conceptSort, setConceptSort] = useState('tracked_users');

  // Monitoring
  const [monitoring, setMonitoring] = useState<any>(null);

  // Governance
  const [govRules, setGovRules] = useState<any[]>([]);
  const [govAudits, setGovAudits] = useState<any[]>([]);
  const [govAuditsTotal, setGovAuditsTotal] = useState(0);
  const [govAcceptance, setGovAcceptance] = useState<any>(null);
  const [govAuditFilter, setGovAuditFilter] = useState<'all' | 'approved' | 'rejected'>('all');
  const [govNewKind, setGovNewKind] = useState('keyword');
  const [govNewPattern, setGovNewPattern] = useState('');

  // DB Inspector
  const [inspectorTables, setInspectorTables] = useState<InspectorTable[]>([]);
  const [inspectorSelectedTable, setInspectorSelectedTable] = useState('');
  const [inspectorColumns, setInspectorColumns] = useState<InspectorColumn[]>([]);
  const [inspectorRows, setInspectorRows] = useState<Record<string, unknown>[]>([]);
  const [inspectorTotalRows, setInspectorTotalRows] = useState(0);
  const [inspectorLimit, setInspectorLimit] = useState(100);
  const [inspectorError, setInspectorError] = useState('');

  useEffect(() => {
    if (!user?.is_admin) return;
    loadOverview();
  }, [user]);

  useEffect(() => {
    if (tab === 'users') loadUsers();
    if (tab === 'questions') loadQuestions();
    if (tab === 'sessions') loadSessions();
    if (tab === 'concepts') loadConcepts();
    if (tab === 'monitoring') loadMonitoring();
    if (tab === 'governance') loadGovernance();
  }, [tab, userSearch, userPage, qTopic, qPage, conceptTopic, conceptPage, conceptSort, govAuditFilter]);

  useEffect(() => {
    if (tab !== 'inspector') return;
    loadInspectorSchema();
  }, [tab]);

  useEffect(() => {
    if (tab !== 'inspector' || !inspectorSelectedTable) return;
    loadInspectorTable(inspectorSelectedTable);
  }, [tab, inspectorSelectedTable, inspectorLimit]);

  // Load top-level overview and top-concepts widgets.
  const loadOverview = async () => {
    try {
      const [ov, tc] = await Promise.all([
        adminFetch<OverviewData>('/api/admin/overview'),
        adminFetch<{ items: any[] }>('/api/admin/top-concepts'),
      ]);
      setOverview(ov);
      setTopConcepts(tc.items);
    } catch { /* ignore */ }
  };

  // Load paginated user list with optional search filter.
  const loadUsers = async () => {
    try {
      const params = new URLSearchParams({ page: String(userPage), per_page: '15' });
      if (userSearch) params.set('search', userSearch);
      const data = await adminFetch<any>(`/api/admin/users?${params}`);
      setUsers(data.items);
      setUsersTotal(data.total);
    } catch { /* ignore */ }
  };

  // Load paginated question inventory with optional topic filter.
  const loadQuestions = async () => {
    try {
      const params = new URLSearchParams({ page: String(qPage), per_page: '15' });
      if (qTopic) params.set('topic', qTopic);
      const data = await adminFetch<any>(`/api/admin/questions?${params}`);
      setQuestions(data.items);
      setQTotal(data.total);
    } catch { /* ignore */ }
  };

  // Load recent sessions across room types.
  const loadSessions = async () => {
    try {
      const data = await adminFetch<any>('/api/admin/sessions');
      setSessions(data.items);
    } catch { /* ignore */ }
  };

  // Load paginated concept analytics table.
  const loadConcepts = async () => {
    try {
      const params = new URLSearchParams({
        page: String(conceptPage),
        per_page: '20',
        sort_by: conceptSort,
      });
      if (conceptTopic) params.set('topic', conceptTopic);
      const data = await adminFetch<any>(`/api/admin/concepts?${params}`);
      setConcepts(data.items);
      setConceptsTotal(data.total);
    } catch { /* ignore */ }
  };

  // Load monitoring metrics and recent operational diagnostics.
  const loadMonitoring = async () => {
    try {
      setMonitoring(await adminFetch('/api/admin/monitoring'));
    } catch { /* ignore */ }
  };

  // Load governance block rules and audit log.
  const loadGovernance = async () => {
    try {
      const [rulesData, auditsData] = await Promise.all([
        adminFetch<{ items: any[] }>('/api/admin/governance/blocked-rules'),
        adminFetch<{ items: any[]; total: number; persist_acceptance: any }>(
          `/api/admin/governance/audits?limit=50${govAuditFilter === 'approved' ? '&approved=true' : govAuditFilter === 'rejected' ? '&approved=false' : ''}`
        ),
      ]);
      setGovRules(rulesData.items || []);
      setGovAudits(auditsData.items || []);
      setGovAuditsTotal(auditsData.total || 0);
      setGovAcceptance(auditsData.persist_acceptance || null);
    } catch { /* ignore */ }
  };

  // Create a new governance block rule.
  const createGovRule = async () => {
    if (!govNewPattern.trim()) return;
    try {
      const res = await fetch(`${API_BASE}/api/admin/governance/blocked-rules`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ kind: govNewKind, pattern: govNewPattern.trim() }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setGovNewPattern('');
      loadGovernance();
    } catch { /* ignore */ }
  };

  // Toggle a governance block rule's active status.
  const toggleGovRule = async (ruleId: string, newActive: boolean) => {
    try {
      const res = await fetch(`${API_BASE}/api/admin/governance/blocked-rules/${ruleId}`, {
        method: 'PATCH',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: newActive }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      loadGovernance();
    } catch { /* ignore */ }
  };

  // Delete a governance block rule.
  const deleteGovRule = async (ruleId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/admin/governance/blocked-rules/${ruleId}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      loadGovernance();
    } catch { /* ignore */ }
  };

  // Load database schema for read-only table inspection.
  const loadInspectorSchema = async () => {
    try {
      const data = await adminFetch<{ tables: InspectorTable[] }>('/api/admin/db/schema');
      const tables = Array.isArray(data.tables) ? data.tables : [];
      setInspectorTables(tables);
      setInspectorError('');
      if (!inspectorSelectedTable && tables.length > 0) {
        setInspectorSelectedTable(tables[0].name);
      }
    } catch (err: any) {
      setInspectorError(err?.message ?? 'Failed to load DB schema.');
    }
  };

  // Load one table's rows and columns for key-value inspection.
  const loadInspectorTable = async (tableName = inspectorSelectedTable) => {
    if (!tableName) return;
    const safeLimit = Math.max(1, Math.min(500, Math.round(inspectorLimit)));
    if (safeLimit !== inspectorLimit) {
      setInspectorLimit(safeLimit);
    }

    try {
      const data = await adminFetch<{
        columns: InspectorColumn[];
        rows: Record<string, unknown>[];
        total: number;
      }>(`/api/admin/db/table/${encodeURIComponent(tableName)}?limit=${safeLimit}&offset=0`);
      setInspectorColumns(Array.isArray(data.columns) ? data.columns : []);
      setInspectorRows(Array.isArray(data.rows) ? data.rows : []);
      setInspectorTotalRows(Number(data.total ?? 0));
      setInspectorError('');
    } catch (err: any) {
      setInspectorColumns([]);
      setInspectorRows([]);
      setInspectorTotalRows(0);
      setInspectorError(err?.message ?? 'Failed to load table rows.');
    }
  };

  // Toggle admin-controlled user flags and refresh user list.
  const toggleUserField = async (userId: string, field: 'is_active' | 'is_admin', value: boolean) => {
    try {
      await adminPatch(`/api/admin/users/${userId}?${field}=${value}`);
      loadUsers();
    } catch { /* ignore */ }
  };

  // Refresh dataset for whichever tab is currently selected.
  const refreshCurrentTab = () => {
    if (tab === 'overview') loadOverview();
    if (tab === 'users') loadUsers();
    if (tab === 'questions') loadQuestions();
    if (tab === 'sessions') loadSessions();
    if (tab === 'concepts') loadConcepts();
    if (tab === 'inspector') {
      loadInspectorSchema();
      if (inspectorSelectedTable) {
        loadInspectorTable(inspectorSelectedTable);
      }
    }
    if (tab === 'monitoring') loadMonitoring();
    if (tab === 'governance') loadGovernance();
  };

  const renderInspectorValue = (value: unknown): string => {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'object') {
      try {
        return JSON.stringify(value);
      } catch {
        return '[object]';
      }
    }
    return String(value);
  };


  // ── Styles (Tailwind overhaul) ──────────────────────────────────────────────

  const tabBtnClass = (active: boolean) => 
    `px-5 py-2 rounded text-xs font-bold uppercase tracking-widest transition-all ${
      active 
        ? 'bg-[#2D1B14] text-[#F5F2E7] shadow-md' 
        : 'bg-transparent text-[#2D1B14]/60 hover:bg-[#2D1B14]/5'
    }`;

  const cardClass = "bg-white p-6 border border-[#2D1B14]/10 shadow-sm";
  
  const thClass = "text-left p-3 text-[10px] font-bold uppercase tracking-widest text-[#2D1B14]/60 border-b border-[#2D1B14]/10";
  const tdClass = "p-3 text-sm text-[#2D1B14] border-b border-[#2D1B14]/5";

  const statCard = (label: string, value: number | string, isAlert: boolean = false) => (
    <div className={`${cardClass} text-center flex flex-col justify-center items-center`}>
      <div className={`text-3xl font-black font-playfair ${isAlert ? 'text-[#e74c3c]' : 'text-[#2D1B14]'}`}>{value}</div>
      <div className="text-[10px] font-bold uppercase tracking-widest text-[#D4AF37] mt-2">{label}</div>
    </div>
  );

  return (
    <InternalLayout>
      <div className="max-w-6xl mx-auto p-8">
        <div className="flex justify-between items-end mb-10">
          <div>
            <h1 className="text-4xl font-black font-playfair text-[#2D1B14] mb-2">Admin Dashboard</h1>
            <p className="text-[#2D1B14]/60 italic">System overview and governance controls.</p>
          </div>
          <button
            onClick={refreshCurrentTab}
            className="px-6 py-3 bg-[#D4AF37] text-white text-xs font-bold uppercase tracking-[0.2em] rounded shadow-lg hover:bg-[#c29e2e] transition-colors"
          >
            Refresh Data
          </button>
        </div>

        {/* Tab Bar */}
        <div className="flex gap-2 mb-10 flex-wrap border-b border-[#2D1B14]/10 pb-4">
          {(['overview', 'users', 'questions', 'sessions', 'concepts', 'governance', 'inspector', 'monitoring'] as Tab[]).map(t => (
            <button key={t} onClick={() => setTab(t)} className={tabBtnClass(tab === t)}>
              {t}
            </button>
          ))}
        </div>

        {/* ── OVERVIEW ── */}
        {tab === 'overview' && overview && (
          <div className="space-y-8">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
              {statCard('Total Users', overview.users.total)}
              {statCard('Active Users', overview.users.active)}
              {statCard('Total Questions', overview.questions.total)}
              {statCard('Total Responses', overview.responses.total)}
              {statCard('Concepts Tracked', overview.concepts.total)}
              {statCard('Challenge Sessions', overview.sessions.challenge)}
              {statCard('Custom Sessions', overview.sessions.custom)}
              {statCard('PvP Matches', overview.pvp.total_matches)}
            </div>

            {/* Top Concepts */}
            {topConcepts.length > 0 && (
              <div className={cardClass}>
                <h3 className="text-xs font-bold uppercase tracking-[0.3em] text-[#D4AF37] mb-6">Top Concepts</h3>
                <div className="space-y-3">
                  {topConcepts.map((c, i) => (
                    <div key={c.concept_id} className={`flex justify-between items-center py-3 ${i < topConcepts.length - 1 ? 'border-b border-[#2D1B14]/5' : ''}`}>
                      <div>
                        <span className="font-bold text-[#2D1B14]">{c.name}</span>
                        <span className="text-[#2D1B14]/50 ml-2 text-sm italic">({c.topic})</span>
                      </div>
                      <div className="text-sm text-[#2D1B14]/70">
                        {c.tracked_users} users | <span className="text-[#D4AF37] font-bold">θ={c.avg_theta}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── USERS ── */}
        {tab === 'users' && (
          <div className={cardClass}>
            <div className="mb-6 flex gap-4">
              <input
                value={userSearch}
                onChange={e => { setUserSearch(e.target.value); setUserPage(1); }}
                placeholder="Search by email or username..."
                className="flex-1 p-3 border border-[#2D1B14]/20 rounded bg-transparent focus:border-[#D4AF37] outline-none text-[#2D1B14]"
              />
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr>
                    <th className={thClass}>Username</th>
                    <th className={thClass}>Email</th>
                    <th className={`${thClass} text-center`}>Points</th>
                    <th className={`${thClass} text-center`}>Active</th>
                    <th className={`${thClass} text-center`}>Admin</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map(u => (
                    <tr key={u.id} className="hover:bg-[#2D1B14]/5 transition-colors">
                      <td className={`${tdClass} font-bold`}>{u.username}</td>
                      <td className={`${tdClass} text-[#2D1B14]/60`}>{u.email}</td>
                      <td className={`${tdClass} text-center font-playfair font-bold text-lg`}>{u.points}</td>
                      <td className={`${tdClass} text-center`}>
                        <button onClick={() => toggleUserField(u.id, 'is_active', !u.is_active)} className={`text-lg ${u.is_active ? 'text-green-600' : 'text-red-600'}`}>
                          {u.is_active ? '✅' : '❌'}
                        </button>
                      </td>
                      <td className={`${tdClass} text-center`}>
                        <button onClick={() => toggleUserField(u.id, 'is_admin', !u.is_admin)} className={`text-lg ${u.is_admin ? 'text-[#D4AF37]' : 'text-gray-300'}`}>
                          {u.is_admin ? '👑' : '—'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex justify-between items-center mt-6 text-xs font-bold uppercase tracking-widest text-[#2D1B14]/60">
              <span>{usersTotal} total users</span>
              <div className="flex gap-4 items-center">
                <button onClick={() => setUserPage(p => Math.max(1, p - 1))} disabled={userPage <= 1} className="hover:text-[#D4AF37] disabled:opacity-30">← Prev</button>
                <span className="text-[#D4AF37]">Page {userPage}</span>
                <button onClick={() => setUserPage(p => p + 1)} disabled={users.length < 15} className="hover:text-[#D4AF37] disabled:opacity-30">Next →</button>
              </div>
            </div>
          </div>
        )}

        {/* ── QUESTIONS ── */}
        {tab === 'questions' && (
          <div className="space-y-6">
            <div className="flex gap-3 mb-4">
              {['', 'history', 'geography'].map(t => (
                <button key={t} onClick={() => { setQTopic(t); setQPage(1); }} className={`px-4 py-2 rounded text-xs uppercase tracking-widest font-bold border ${qTopic === t ? 'bg-[#D4AF37] text-white border-[#D4AF37]' : 'border-[#2D1B14]/20 text-[#2D1B14]/60 hover:border-[#D4AF37]'}`}>
                  {t || 'All Topics'}
                </button>
              ))}
            </div>

            <div className="space-y-4">
              {questions.map(q => (
                <div key={q.id} className={`${cardClass} flex justify-between items-center`}>
                  <div className="flex-1">
                    <div className="text-[#2D1B14] font-medium">{q.question_text || q.text || '(no question text)'}</div>
                    <div className="flex gap-4 mt-3 text-xs uppercase tracking-widest text-[#2D1B14]/50">
                      <span><span className="text-[#D4AF37]">Topic:</span> {q.topic}</span>
                      <span><span className="text-[#D4AF37]">IRT:</span> {q.difficulty_irt}</span>
                      <span><span className="text-[#D4AF37]">Seen:</span> {q.times_seen}x</span>
                      {q.gov_approved === false && <span className="bg-red-100 text-red-600 px-2 py-0.5 rounded font-bold">BLOCKED</span>}
                      {q.gov_approved === true && <span className="bg-green-100 text-green-600 px-2 py-0.5 rounded font-bold">APPROVED</span>}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="flex justify-between items-center mt-6 text-xs font-bold uppercase tracking-widest text-[#2D1B14]/60">
              <span>{qTotal} total questions</span>
              <div className="flex gap-4 items-center">
                <button onClick={() => setQPage(p => Math.max(1, p - 1))} disabled={qPage <= 1} className="hover:text-[#D4AF37] disabled:opacity-30">← Prev</button>
                <span className="text-[#D4AF37]">Page {qPage}</span>
                <button onClick={() => setQPage(p => p + 1)} disabled={questions.length < 15} className="hover:text-[#D4AF37] disabled:opacity-30">Next →</button>
              </div>
            </div>
          </div>
        )}

        {/* ── SESSIONS ── */}
        {tab === 'sessions' && (
          <div className="space-y-4">
            {sessions.length === 0 && <p className="text-[#2D1B14]/50 italic">No sessions found</p>}
            {sessions.map(s => (
              <div key={s.id} className={`${cardClass} flex justify-between items-center`}>
                <div className="flex items-center gap-4">
                  <span className={`px-3 py-1 text-xs font-bold uppercase tracking-widest rounded ${s.type === 'challenge' ? 'bg-red-100 text-red-600' : 'bg-blue-100 text-blue-600'}`}>
                    {s.type}
                  </span>
                  <span className="text-[#2D1B14] font-medium">{s.topic}</span>
                </div>
                <div className="text-sm font-bold text-[#2D1B14]/60">
                  <span className="text-[#D4AF37] text-lg">{s.correct}</span> / {s.questions} correct
                  <span className="ml-4">{s.is_completed ? '✅' : '⏳'}</span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ── CONCEPTS ── */}
        {tab === 'concepts' && (
          <div className={cardClass}>
            <div className="flex gap-4 mb-6">
              <select
                value={conceptTopic}
                onChange={e => { setConceptTopic(e.target.value); setConceptPage(1); }}
                className="p-3 border border-[#2D1B14]/20 rounded bg-transparent outline-none text-[#2D1B14] text-sm focus:border-[#D4AF37]"
              >
                <option value="">All Topics</option>
                <option value="history">History</option>
                <option value="geography">Geography</option>
                <option value="mixed">Mixed</option>
              </select>

              <select
                value={conceptSort}
                onChange={e => { setConceptSort(e.target.value); setConceptPage(1); }}
                className="p-3 border border-[#2D1B14]/20 rounded bg-transparent outline-none text-[#2D1B14] text-sm focus:border-[#D4AF37]"
              >
                <option value="tracked_users">Sort: Users (↑)</option>
                <option value="name">Sort: Name</option>
                <option value="topic">Sort: Topic</option>
                <option value="avg_theta">Sort: Avg Mastery</option>
                <option value="questions_tagged">Sort: Questions</option>
              </select>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr>
                    <th className={thClass}>Concept Name</th>
                    <th className={thClass}>Topic</th>
                    <th className={`${thClass} text-center`}>Users</th>
                    <th className={`${thClass} text-center`}>Avg θ</th>
                    <th className={`${thClass} text-center`}>Questions</th>
                  </tr>
                </thead>
                <tbody>
                  {concepts.map(c => (
                    <tr key={c.concept_id} className="hover:bg-[#2D1B14]/5 transition-colors">
                      <td className={`${tdClass} font-bold`}>{c.name}</td>
                      <td className={`${tdClass} text-[#2D1B14]/60 uppercase text-xs tracking-widest`}>{c.topic}</td>
                      <td className={`${tdClass} text-center font-bold`}>{c.tracked_users}</td>
                      <td className={`${tdClass} text-center text-[#D4AF37] font-bold`}>{c.avg_theta}</td>
                      <td className={`${tdClass} text-center`}>{c.questions_tagged}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex justify-between items-center mt-6 text-xs font-bold uppercase tracking-widest text-[#2D1B14]/60">
              <span>{conceptsTotal} total concepts</span>
              <div className="flex gap-4 items-center">
                <button onClick={() => setConceptPage(p => Math.max(1, p - 1))} disabled={conceptPage <= 1} className="hover:text-[#D4AF37] disabled:opacity-30">← Prev</button>
                <span className="text-[#D4AF37]">Page {conceptPage}</span>
                <button onClick={() => setConceptPage(p => p + 1)} disabled={concepts.length < 20} className="hover:text-[#D4AF37] disabled:opacity-30">Next →</button>
              </div>
            </div>
          </div>
        )}

        {/* ── GOVERNANCE ── */}
        {tab === 'governance' && (
          <div className="space-y-8">
            {govAcceptance && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                {statCard('Total Evaluated', govAcceptance.total)}
                {statCard('Approved', govAcceptance.approved)}
                {statCard('Rejected', govAcceptance.total - govAcceptance.approved, true)}
                {statCard('Acceptance Rate', govAcceptance.rate ? `${(govAcceptance.rate * 100).toFixed(1)}%` : '—')}
              </div>
            )}

            <div className={cardClass}>
              <h3 className="text-xs font-bold uppercase tracking-[0.3em] text-[#D4AF37] mb-6">Block Rules</h3>
              
              <div className="flex gap-4 mb-6">
                <select
                  value={govNewKind}
                  onChange={e => setGovNewKind(e.target.value)}
                  className="p-3 border border-[#2D1B14]/20 rounded bg-transparent outline-none text-[#2D1B14]"
                >
                  <option value="keyword">Keyword</option>
                  <option value="topic">Topic</option>
                </select>
                <input
                  value={govNewPattern}
                  onChange={e => setGovNewPattern(e.target.value)}
                  placeholder="Pattern to block..."
                  onKeyDown={e => e.key === 'Enter' && createGovRule()}
                  className="flex-1 p-3 border border-[#2D1B14]/20 rounded bg-transparent focus:border-[#D4AF37] outline-none text-[#2D1B14]"
                />
                <button onClick={createGovRule} className="px-6 py-3 bg-[#e74c3c] text-white text-xs font-bold uppercase tracking-widest rounded hover:bg-[#c0392b] transition-colors">
                  + Add Rule
                </button>
              </div>

              {govRules.length > 0 && (
                <table className="w-full text-left border-collapse mt-4">
                  <thead>
                    <tr>
                      <th className={thClass}>Kind</th>
                      <th className={thClass}>Pattern</th>
                      <th className={`${thClass} text-center`}>Active</th>
                      <th className={`${thClass} text-center`}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {govRules.map(r => (
                      <tr key={r.id} className="hover:bg-[#2D1B14]/5">
                        <td className={tdClass}>
                          <span className={`px-2 py-1 text-[10px] font-bold uppercase tracking-widest rounded ${r.kind === 'topic' ? 'bg-purple-100 text-purple-700' : 'bg-blue-100 text-blue-700'}`}>{r.kind}</span>
                        </td>
                        <td className={`${tdClass} font-mono text-xs`}>{r.pattern}</td>
                        <td className={`${tdClass} text-center`}>
                          <button onClick={() => toggleGovRule(r.id, !r.is_active)} className="text-lg">
                            {r.is_active ? '✅' : '❌'}
                          </button>
                        </td>
                        <td className={`${tdClass} text-center`}>
                          <button onClick={() => deleteGovRule(r.id)} className="text-xs font-bold text-red-600 hover:underline uppercase tracking-widest">Delete</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className={cardClass}>
              <div className="flex justify-between items-center mb-6">
                <h3 className="text-xs font-bold uppercase tracking-[0.3em] text-[#D4AF37]">Audit Log ({govAuditsTotal})</h3>
                <div className="flex gap-2">
                  {(['all', 'approved', 'rejected'] as const).map(f => (
                    <button key={f} onClick={() => setGovAuditFilter(f)} className={`px-3 py-1 border text-[10px] font-bold uppercase tracking-widest rounded ${govAuditFilter === f ? 'bg-[#D4AF37] text-white border-[#D4AF37]' : 'border-[#2D1B14]/20 text-[#2D1B14]/60'}`}>
                      {f}
                    </button>
                  ))}
                </div>
              </div>

              {govAudits.map(a => (
                <div key={a.id} className="flex justify-between items-center py-3 border-b border-[#2D1B14]/5 text-sm">
                  <div className="flex items-center gap-4">
                    <span>{a.approved ? '✅' : '❌'}</span>
                    <span className="font-bold">{a.room}</span>
                    <span className="text-[#2D1B14]/60 uppercase tracking-widest text-[10px]">{a.action}</span>
                    <span className="italic">{a.topic}</span>
                  </div>
                  <div className="flex items-center gap-4">
                    {a.reasons && a.reasons.length > 0 && <span className="text-red-500 text-xs font-bold">{a.reasons.join(', ')}</span>}
                    <span className="text-[#2D1B14]/40 text-xs">{a.created_at ? new Date(a.created_at).toLocaleString() : ''}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── INSPECTOR ── */}
        {tab === 'inspector' && (
          <div className="space-y-6">
            <div className={cardClass}>
              <div className="flex gap-4 flex-wrap items-end">
                <div className="flex flex-col flex-1 min-w-[200px]">
                  <label className="text-[10px] font-bold uppercase tracking-widest text-[#2D1B14]/60 mb-2">Table</label>
                  <select
                    value={inspectorSelectedTable}
                    onChange={e => setInspectorSelectedTable(e.target.value)}
                    className="p-3 border border-[#2D1B14]/20 rounded bg-transparent focus:border-[#D4AF37] outline-none text-[#2D1B14]"
                  >
                    {inspectorTables.map(table => (
                      <option key={table.name} value={table.name}>{table.name} ({table.row_count} rows)</option>
                    ))}
                  </select>
                </div>
                
                <div className="flex flex-col w-24">
                  <label className="text-[10px] font-bold uppercase tracking-widest text-[#2D1B14]/60 mb-2">Rows</label>
                  <input
                    type="number" min={1} max={500}
                    value={inspectorLimit}
                    onChange={e => setInspectorLimit(Number(e.target.value || 100))}
                    className="p-3 border border-[#2D1B14]/20 rounded bg-transparent focus:border-[#D4AF37] outline-none text-[#2D1B14] text-center"
                  />
                </div>

                <button onClick={() => loadInspectorSchema()} className="px-4 py-3 bg-[#2D1B14] text-white text-xs font-bold uppercase tracking-widest rounded hover:bg-[#3d261c] transition-colors">Reload Schema</button>
                <button onClick={() => loadInspectorTable(inspectorSelectedTable)} className="px-4 py-3 bg-[#D4AF37] text-white text-xs font-bold uppercase tracking-widest rounded hover:bg-[#c29e2e] transition-colors">Load Table</button>
              </div>
            </div>

            {inspectorError && (
              <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded text-sm font-bold">
                {inspectorError}
              </div>
            )}

            {inspectorColumns.length > 0 && (
              <div className={`${cardClass} overflow-x-auto`}>
                <div className="text-[10px] font-bold uppercase tracking-widest text-[#D4AF37] mb-4">Columns</div>
                <div className="flex gap-2 flex-wrap mb-6">
                  {inspectorColumns.map(col => (
                    <span key={col.name} className="border border-[#2D1B14]/20 rounded-full px-3 py-1 text-xs text-[#2D1B14]/70">
                      <span className="font-bold text-[#2D1B14]">{col.name}</span> ({col.type})
                      {col.primary_key && <span className="text-[#D4AF37] font-bold ml-1">PK</span>}
                      {!col.nullable && <span className="text-red-500 ml-1">*</span>}
                    </span>
                  ))}
                </div>

                <div className="overflow-x-auto max-h-[600px] border border-[#2D1B14]/10">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead className="bg-[#2D1B14]/5 sticky top-0">
                      <tr>
                        {inspectorColumns.map(col => (
                          <th key={col.name} className="p-3 border-b border-[#2D1B14]/10 font-bold text-[#2D1B14]/70 whitespace-nowrap">{col.name}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {inspectorRows.map((row, idx) => (
                        <tr key={idx} className="hover:bg-[#2D1B14]/5 border-b border-[#2D1B14]/5">
                          {inspectorColumns.map(col => (
                            <td key={col.name} className="p-3 whitespace-nowrap text-[#2D1B14]/80 font-mono">
                              {renderInspectorValue(row[col.name])}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── MONITORING ── */}
        {tab === 'monitoring' && monitoring && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            {statCard('Total Requests', monitoring.total_requests)}
            {statCard('Total Errors', monitoring.total_errors, true)}
            {statCard('Rate Limits', monitoring.total_rate_limits, true)}
            {statCard('Recent Errors', monitoring.recent_errors_count, true)}
            
            {Object.entries(monitoring.endpoints || {}).map(([ep, count]) => (
              <div key={ep} className={cardClass}>
                <div className="text-[10px] font-bold uppercase tracking-widest text-[#D4AF37] mb-2 truncate" title={ep}>{ep}</div>
                <div className="text-2xl font-black font-playfair text-[#2D1B14]">{String(count)}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </InternalLayout>
  );
}
