'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { Activity, ArrowDownLeft, ArrowLeft, ArrowRight, Bot, Check, CheckCheck, ChevronDown,
  ChevronRight, CircleAlert, Clock3, Command, Database, FileCheck2, FlaskConical, GitBranch,
  LayoutDashboard, LoaderCircle, Menu, Network, Play, Plus, Radar, RefreshCw, Search,
  Server, ShieldCheck, Terminal, TriangleAlert, Workflow, X, Zap } from 'lucide-react';
import { Background, Controls, MarkerType, ReactFlow, type Node } from '@xyflow/react';
import { api, date, human, number, percent, short, type Data } from '@/lib/api';

function useData<T = Data>(path: string, interval = 3500) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const alive = useRef(true);
  const inFlight = useRef<string | null>(null);
  const currentPath = useRef(path);
  currentPath.current = path;
  const reload = useCallback(async () => {
    if (inFlight.current === path) return;
    inFlight.current = path;
    try { const value = await api<T>(path); if (alive.current && currentPath.current === path) { setData(value); setError(''); } }
    catch (e) { if (alive.current && currentPath.current === path) setError(e instanceof Error ? e.message : 'UNAVAILABLE'); }
    finally { if (inFlight.current === path) inFlight.current = null; if (alive.current && currentPath.current === path) setLoading(false); }
  }, [path]);
  useEffect(() => {
    alive.current = true; setLoading(true); setData(null); void reload();
    const timer = window.setInterval(reload, interval);
    return () => { alive.current = false; window.clearInterval(timer); };
  }, [reload, interval]);
  return { data, error, loading, reload };
}

function Badge({ value }: { value?: string }) {
  const key = (value || 'unknown').toLowerCase();
  const color = ['healthy', 'verified', 'completed', 'approved', 'pass', 'ok', 'consumed'].includes(key) ? 'green'
    : ['degraded', 'open', 'pending', 'awaiting_approval', 'running', 'queued', 'fixture'].includes(key) ? 'amber'
    : ['failed', 'fail', 'revoked', 'rejected', 'expired', 'timed_out', 'blocked', 'interrupted'].includes(key) ? 'red' : 'blue';
  return <span className={`badge ${color}`}><span className="dot" style={{ background: 'currentColor', width: 4, height: 4 }} />{human(value)}</span>;
}
function Empty({ children = 'No records yet.' }: { children?: React.ReactNode }) {
  return <div className="empty"><Database size={24} />{children}</div>;
}
function ErrorNotice({ error, retry }: { error: string; retry?: () => void }) {
  if (!error) return null;
  return <div className="notice error" role="alert"><CircleAlert size={16} /><div><strong>{retry ? 'Unable to load current data' : 'Request could not be completed'}</strong><p>{human(error)}{retry ? '. Displayed records may be stale.' : ''}</p></div>{retry && <button onClick={retry}>Retry</button>}</div>;
}
function Stat({ title, value, foot, icon: Icon = Activity }: { title: string; value: React.ReactNode; foot: string; icon?: typeof Activity }) {
  return <div className="stat"><div className="stat-top">{title}<span className="stat-icon"><Icon size={15} /></span></div><div className="stat-value">{value}</div><div className="stat-foot">{foot}</div></div>;
}
function Card({ title, children, extra }: { title: string; children: React.ReactNode; extra?: React.ReactNode }) {
  return <section className="card"><div className="card-header"><h2>{title}</h2>{extra}</div>{children}</section>;
}
function Json({ value }: { value: unknown }) { return <pre className="json">{JSON.stringify(value, null, 2)}</pre>; }
function Property({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="property"><span>{label}</span><span>{children}</span></div>;
}
function Modal({ title, close, children }: { title: string; close: () => void; children: React.ReactNode }) {
  const id = useId();
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(close);
  closeRef.current = close;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const first = ref.current?.querySelector<HTMLElement>('input, button, select'); first?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeRef.current();
      if (event.key === 'Tab' && ref.current) {
        const items = [...ref.current.querySelectorAll<HTMLElement>('button:not(:disabled), input, select, a[href]')];
        const first = items[0], last = items.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener('keydown', key);
    return () => { document.removeEventListener('keydown', key); previous?.focus(); };
  }, []);
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) close(); }}><div className="modal" role="dialog" aria-modal="true" aria-labelledby={id} ref={ref}><div className="modal-head"><h2 id={id}>{title}</h2><button className="icon" onClick={close} aria-label="Close dialog"><X size={16} /></button></div><div className="modal-body">{children}</div></div></div>;
}

const navigation = [
  { href: '/', label: 'Overview', icon: LayoutDashboard },
  { href: '/incidents', label: 'Incidents', icon: CircleAlert },
  { href: '/workspace', label: 'Agent workspace', icon: Bot },
  { href: '/approvals', label: 'Approval center', icon: ShieldCheck },
  { href: '/evaluations', label: 'Evaluations', icon: FlaskConical },
  { href: '/architecture', label: 'System architecture', icon: Network },
];

export default function Dashboard() {
  const path = usePathname();
  const router = useRouter();
  const meta = useData('meta', 5000);
  const health = useData('health/ready', 5000);
  const [menu, setMenu] = useState(false);
  const [dialog, setDialog] = useState<'login' | 'simulate' | null>(null);
  const page = navigation.find(item => item.href === '/' ? path === '/' : path.startsWith(item.href));
  const session = meta.data?.session;
  const onSimulate = () => setDialog(session ? 'simulate' : 'login');
  return <div className="app"><aside className={`sidebar ${menu ? 'open' : ''}`} aria-label="Main navigation">
    <Link href="/" className="brand" onClick={() => setMenu(false)}><span className="brand-mark"><Radar size={24} /></span>OpsPilot <small>AI</small></Link>
    <div className="nav-label">Workspace</div><nav>{navigation.map(item => <Link key={item.href} href={item.href} className={`nav-link ${page?.href === item.href ? 'active' : ''}`} aria-current={page?.href === item.href ? 'page' : undefined} onClick={() => setMenu(false)}><item.icon size={17} />{item.label}</Link>)}</nav>
    <div className="sidebar-footer"><div className="sandbox"><ShieldCheck size={18} color="#5a9b83" /><div><strong>Local sandbox</strong><span className="muted">Isolated simulated services</span></div></div><p>OPSPILOT AI · STAGE 06</p></div>
  </aside><div className="content"><header className="topbar"><div className="breadcrumb"><button className="icon mobile-toggle" aria-label="Toggle navigation" onClick={() => setMenu(!menu)}><Menu size={17} /></button><span>Workspace</span><ChevronRight size={12} /><b>{page?.label || 'Page not found'}</b></div><div className="top-actions"><span className="connection" role="status"><i className={`dot ${health.error ? 'bad' : ''}`} />{health.loading ? 'Checking backend' : health.error ? 'Backend disconnected' : 'Backend connected'}</span><div className="divider" /><button className="operator" onClick={async () => { if (session) { await api('session', 'DELETE'); void meta.reload(); } else setDialog('login'); }}><span className="avatar">{session ? 'OP' : 'RO'}</span><span className="operator-name">{session ? session.subject : 'Sign in as operator'}</span><ChevronDown size={12} /></button></div></header>
    <main><ErrorNotice error={health.error} retry={health.reload} />
      {path === '/' ? <Overview simulate={onSimulate} meta={meta.data} />
        : path === '/incidents' ? <IncidentList simulate={onSimulate} />
        : path.startsWith('/incidents/') ? <IncidentDetail id={path.split('/')[2]} meta={meta.data} login={() => setDialog('login')} />
        : path === '/workspace' ? <RunList />
        : path.startsWith('/workspace/') ? <Workspace id={path.split('/')[2]} />
        : path === '/approvals' ? <Approvals meta={meta.data} login={() => setDialog('login')} />
        : path === '/evaluations' ? <Evaluations />
        : path === '/architecture' ? <Architecture />
        : <Empty>Page not found. <Link href="/">Return to overview</Link></Empty>}
      <footer className="footer-line"><span>OpsPilot AI · Autonomous incident response, with human oversight</span><span>LOCAL ENVIRONMENT / NO PRODUCTION CONNECTIONS</span></footer>
    </main></div>
    {dialog === 'login' && <Login close={() => setDialog(null)} done={() => { setDialog(null); void meta.reload(); }} />}
    {dialog === 'simulate' && <Simulation close={() => setDialog(null)} done={id => { setDialog(null); router.push(`/incidents/${id}`); }} />}
  </div>;
}

function Login({ close, done }: { close: () => void; done: () => void }) {
  const [token, setToken] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  return <Modal title="Operator sign in" close={close}><p className="subtitle" style={{ marginBottom: 20 }}>Authenticate with a locally provisioned human operator credential. This session expires after 30 minutes.</p><form onSubmit={async e => { e.preventDefault(); setBusy(true); setError(''); try { await api('session', 'POST', { credential: token }); setToken(''); done(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } }}><label htmlFor="credential">Operator credential</label><input id="credential" type="password" autoComplete="current-password" value={token} onChange={e => setToken(e.target.value)} minLength={32} maxLength={256} required /><ErrorNotice error={error} /><div className="notice"><ShieldCheck size={16} /><p>Approval authority comes from your backend identity and resource permissions. Agent requests cannot grant approval.</p></div><div className="form-actions"><button type="button" onClick={close}>Cancel</button><button className="primary" disabled={busy}>{busy ? <LoaderCircle size={15} /> : <ShieldCheck size={15} />}Sign in</button></div></form></Modal>;
}

function Simulation({ close, done }: { close: () => void; done: (id: string) => void }) {
  const [service, setService] = useState('checkout-service'); const [scenario, setScenario] = useState('worker-saturation');
  const [confirmed, setConfirmed] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const options = service === 'checkout-service' ? ['worker-saturation', 'slow-checkout', 'bad-config'] : service === 'payment-service' ? ['worker-saturation', 'payment-unavailable'] : ['worker-saturation', 'inventory-db-exhaustion'];
  return <Modal title="Start a simulated incident" close={close}><p className="subtitle" style={{ marginBottom: 20 }}>Generate real simulator traffic and capture the resulting metrics and incident.</p><label htmlFor="service">Target service</label><select id="service" value={service} onChange={e => { setService(e.target.value); setScenario('worker-saturation'); setConfirmed(false); }}>{['checkout-service', 'payment-service', 'inventory-service'].map(s => <option key={s}>{s}</option>)}</select><label htmlFor="scenario">Fault scenario</label><select id="scenario" value={scenario} onChange={e => setScenario(e.target.value)}>{options.map(s => <option key={s} value={s}>{human(s.replaceAll('-', '_'))}</option>)}</select><div className="notice warn"><TriangleAlert size={16} /><p>The selected service fixture will be reset before injection. Other fixtures are preserved. Existing approvals for this target may become stale.</p></div><label className="check"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />I authorize resetting only {service} and activating this sandbox fault.</label><ErrorNotice error={error} /><div className="form-actions"><button onClick={close}>Cancel</button><button className="primary" disabled={!confirmed || busy} onClick={async () => { setBusy(true); try { const value = await api('simulation', 'POST', { service_name: service, scenario_id: scenario }); done(value.incident_id); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } }}><Zap size={15} />{busy ? 'Generating traffic…' : 'Start incident'}</button></div></Modal>;
}

function IncidentTable({ items }: { items: Data[] }) {
  if (!items.length) return <Empty>No open incidents. Start a sandbox scenario to investigate.</Empty>;
  return <div className="table-wrap"><table><thead><tr><th>Incident</th><th>Service</th><th>Status</th><th>Detected</th><th /></tr></thead><tbody>{items.map(item => <tr key={item.id}><td><Link href={`/incidents/${item.id}`}><span className="mono">INC-{short(item.id)}</span></Link></td><td>{item.service_name}</td><td><Badge value={item.status} /></td><td>{date(item.opened_at)}</td><td><Link href={`/incidents/${item.id}`} aria-label={`Open incident ${short(item.id)}`}><ArrowRight size={14} /></Link></td></tr>)}</tbody></table></div>;
}
function RunTable({ items }: { items: Data[] }) {
  if (!items.length) return <Empty>No investigations have been recorded.</Empty>;
  return <div className="table-wrap"><table><thead><tr><th>Run</th><th>Target</th><th>Execution mode</th><th>Status</th><th>Started</th><th /></tr></thead><tbody>{items.map(item => <tr key={item.id}><td><Link href={`/workspace/${item.id}`}><span className="mono">RUN-{short(item.id)}</span></Link></td><td>{item.service_name}</td><td><Badge value={item.mode} /></td><td><Badge value={item.status} /></td><td>{date(item.created_at)}</td><td><Link href={`/workspace/${item.id}`} aria-label={`Open run ${short(item.id)}`}><ArrowRight size={14} /></Link></td></tr>)}</tbody></table></div>;
}

function Overview({ simulate, meta }: { simulate: () => void; meta: Data | null }) {
  const { data, error, loading, reload } = useData('overview');
  const open = data?.incidents.filter((item: Data) => item.status === 'open') || [];
  const pending = data?.approvals.filter((item: Data) => item.approval.state === 'pending') || [];
  const events = (data?.approvals || []).flatMap((r: Data) => r.complete_audit_timeline.map((e: Data) => ({ ...e, run_id: r.run_id }))).sort((a: Data, b: Data) => b.at.localeCompare(a.at)).slice(0, 5);
  return <><div className="page-heading"><div><h1>Operations overview</h1><p className="subtitle">Your services, investigations and decisions. In one place.</p></div><div className="heading-actions"><button className="icon" aria-label="Refresh overview" onClick={reload}><RefreshCw size={15} /></button><button className="primary" onClick={simulate}><Plus size={16} />Simulate incident</button></div></div>
    <ErrorNotice error={error} retry={reload} />
    {meta && !meta.real_model_available && <div className="notice"><Bot size={16} /><div><strong>Real model not configured.</strong> The investigation workflow is available in explicitly labeled fixture mode. No LLM inference occurs in fixture runs.</div><Link href="/architecture" style={{ marginLeft: 'auto', whiteSpace: 'nowrap' }}>View architecture <ArrowRight size={11} style={{ display: 'inline' }} /></Link></div>}
    {loading ? <><div className="skeleton" /><div className="skeleton" /></> : data && <>
      <div className="stats"><Stat title="Open incidents" value={open.length} foot="Observed simulator incidents" icon={CircleAlert} /><Stat title="Agent investigations" value={data.runs.length} foot="Most recent 50 persisted runs" icon={Bot} /><Stat title="Pending approvals" value={pending.length} foot="Awaiting a human decision" icon={ShieldCheck} /><Stat title="Verified recoveries" value={data.approvals.filter((r: Data) => r.status === 'verified').length} foot="Within the latest 50 action runs" icon={CheckCheck} /></div>
      <div className="section-head"><h2>Service health <span className="muted" style={{ fontWeight: 400, marginLeft: 7 }}> / {data.services.length} services</span></h2><span className="eyebrow" style={{ fontSize: 8 }}>Latest observed metric window</span></div>
      <div className="service-grid">{data.services.map((service: Data) => <article className="card card-pad" key={service.name}><div className="service-title"><div className="service-name"><Server size={17} />{service.name}</div><Badge value={service.status} /></div><p className="service-sub">{service.name === 'checkout-service' ? 'Orchestration service' : service.name === 'payment-service' ? 'Payment authorization' : 'Stock reservation'}</p><div className="service-values"><div><span>P95 LATENCY</span><strong>{number(service.metric?.p95_latency_ms)} <small>ms</small></strong></div><div><span>ERROR RATE</span><strong>{percent(service.metric?.error_rate)}</strong></div><div><span>REQUESTS</span><strong>{number(service.metric?.requests)}</strong></div></div><div className="util"><span>Worker utilization</span><div className="bar"><i className={service.metric?.worker_utilization >= .9 ? 'bad' : ''} style={{ width: `${Math.min(100, (service.metric?.worker_utilization || 0) * 100)}%` }} /></div><span>{percent(service.metric?.worker_utilization)}</span></div></article>)}</div>
      <div className="two-col"><div><div className="section-head"><h2>Open incidents</h2><Link href="/incidents">View all <ArrowRight size={12} /></Link></div><div className="card"><IncidentTable items={open.slice(0, 5)} /></div></div><div><div className="section-head"><h2>Recent activity</h2><Link href="/approvals">Audit trail <ArrowRight size={12} /></Link></div><div className="card"><div className="activity">{events.length ? events.map((e: Data, i: number) => <div className="activity-item" key={`${e.run_id}-${i}`}><div className="activity-icon"><GitBranch size={12} /></div><div className="activity-copy"><p>{human(e.kind || e.tool)}</p><small>RUN-{short(e.run_id)} · {date(e.at)}</small></div></div>) : <Empty>No action audit events yet.</Empty>}</div></div></div></div>
      <div className="section-head"><h2>Recent agent runs</h2><Link href="/workspace">Open workspace <ArrowRight size={12} /></Link></div><div className="card"><RunTable items={data.runs.slice(0, 5)} /></div>
    </>}
  </>;
}

function IncidentList({ simulate }: { simulate: () => void }) {
  const { data, error, loading, reload } = useData<Data[]>('incidents'); const [filter, setFilter] = useState('all');
  return <><div className="page-heading"><div><h1>Incidents</h1><p className="subtitle">Observed symptoms, evidence and investigation history.</p></div><button className="primary" onClick={simulate}><Plus size={16} />Simulate incident</button></div><ErrorNotice error={error} retry={reload} /><div className="tabs">{['all', 'open', 'resolved'].map(f => <button key={f} className={filter === f ? 'active' : ''} onClick={() => setFilter(f)}>{human(f)}</button>)}</div>{loading ? <div className="skeleton" /> : <div className="card"><IncidentTable items={(data || []).filter(item => filter === 'all' || item.status === filter)} /></div>}</>;
}

function Chart({ metrics }: { metrics: Data[] }) {
  const values = [...metrics].reverse();
  if (!values.length) return <Empty>No metric windows recorded.</Empty>;
  const maximum = Math.max(250, ...values.map(m => m.p95_latency_ms));
  const points = values.map((v, i) => `${28 + i * 550 / Math.max(1, values.length - 1)},${140 - v.p95_latency_ms / maximum * 110}`).join(' ');
  return <><div className="chart-label"><span>P95 latency / ms</span><span>Last {values.length} recorded windows</span></div><svg viewBox="0 0 610 160" className="metric-chart" role="img" aria-label={`Recorded p95 latency ranges from ${Math.min(...values.map(v => v.p95_latency_ms))} to ${maximum} milliseconds`}>{[30, 85, 140].map(y => <line key={y} x1="28" y1={y} x2="590" y2={y} stroke="#eaf0f1" strokeDasharray="3 4" />)}<polyline points={points} fill="none" stroke="#26a17d" strokeWidth="2.5" />{values.map((v, i) => <circle key={i} cx={28 + i * 550 / Math.max(1, values.length - 1)} cy={140 - v.p95_latency_ms / maximum * 110} r="3.5" fill="#26a17d"><title>{date(v.created_at)}: {v.p95_latency_ms}ms</title></circle>)}</svg><div className="chart-label"><span>{date(values[0].created_at)}</span><span>{date(values.at(-1)?.created_at)}</span></div></>;
}

function IncidentDetail({ id, meta, login }: { id: string; meta: Data | null; login: () => void }) {
  const { data, error, loading, reload } = useData(`incidents/${id}`); const runs = useData<Data[]>('runs'); const [launch, setLaunch] = useState(false);
  const related = (runs.data || []).filter(r => r.incident_id === id);
  const latest = data?.metrics[0];
  return <><Link href="/incidents" className="back"><ArrowLeft size={12} />All incidents</Link><div className="page-heading"><div><div className="inline"><h1>INC-{short(id)}</h1>{data && <Badge value={data.status} />}</div><p className="subtitle">{data?.service_name || 'Incident details'} · Detected {date(data?.opened_at)}</p></div><button className="primary" disabled={data?.status !== 'open'} onClick={() => meta?.session ? setLaunch(true) : login()}><Bot size={16} />Launch investigation</button></div><ErrorNotice error={error} retry={reload} />{loading ? <div className="skeleton" /> : data && <>
    <div className="stats"><Stat title="P95 latency" value={number(latest?.p95_latency_ms, ' ms')} foot="Latest service metric window" icon={Clock3} /><Stat title="Error rate" value={percent(latest?.error_rate)} foot={`${number(latest?.errors)} observed errors`} icon={TriangleAlert} /><Stat title="Worker utilization" value={percent(latest?.worker_utilization)} foot="Measured simulated worker occupancy" icon={Server} /><Stat title="Investigations" value={related.length} foot="Runs associated with this incident" icon={Bot} /></div>
    <div className="detail-grid"><div className="stack"><Card title="Observed latency"><div className="card-pad"><Chart metrics={data.metrics} /></div></Card><Card title="Request logs" extra={<span className="muted" style={{ fontSize: 10 }}>Bounded to 100 rows · untrusted telemetry</span>}>{data.logs.length ? <div className="table-wrap"><table><thead><tr><th>Timestamp</th><th>Level</th><th>HTTP status</th><th>Latency</th><th>Evidence ID</th></tr></thead><tbody>{data.logs.map((log: Data) => <tr key={log.id}><td>{date(log.created_at)}</td><td><Badge value={log.level} /></td><td>{log.status_code}</td><td>{number(log.latency_ms, ' ms')}</td><td className="mono">{short(log.id)}</td></tr>)}</tbody></table></div> : <Empty>No incident logs.</Empty>}</Card></div><div className="stack"><Card title="Incident timeline"><div className="activity">{data.events.map((event: Data) => <div className="activity-item" key={event.id}><div className="activity-icon"><Activity size={12} /></div><div className="activity-copy"><p>{human(event.kind)}</p><small>{date(event.created_at)}</small></div></div>)}</div></Card><Card title="Root-cause investigation"><div className="card-pad">{related.length ? related.map(r => <Link key={r.id} href={`/workspace/${r.id}`} className="property"><span>RUN-{short(r.id)}<br /><small>{r.mode} execution</small></span><Badge value={r.status} /></Link>) : <p className="muted">No diagnosis has been made. Launch an investigation to gather evidence through MCP.</p>}</div></Card></div></div>
    </>}{launch && <Launch incident={id} meta={meta} close={() => setLaunch(false)} />}</>;
}

function Launch({ incident, meta, close }: { incident: string; meta: Data | null; close: () => void }) {
  const router = useRouter(); const [mode, setMode] = useState(meta?.real_model_available ? 'real' : 'fixture'); const [budget, setBudget] = useState('180'); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const requestId = useRef(crypto.randomUUID());
  return <Modal title="Launch investigation" close={close}><form onSubmit={async event => { event.preventDefault(); setBusy(true); try { const result = await api('runs', 'POST', { request_id: requestId.current, incident_id: incident, mode, max_seconds: Number(budget) }); router.push(`/workspace/${result.run_id}`); close(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } }}><label htmlFor="mode">Execution mode</label><select id="mode" value={mode} onChange={e => setMode(e.target.value)}><option value="real" disabled={!meta?.real_model_available}>Real model {meta?.real_model_available ? '' : '· not configured'}</option><option value="fixture">Deterministic fixture · no LLM inference</option></select><label htmlFor="budget">Time budget (seconds)</label><input id="budget" type="number" min="0.1" max="180" step="0.1" required value={budget} onChange={e => setBudget(e.target.value)} /><div className="notice"><ShieldCheck size={16} /><p>The investigator can call read-only MCP tools. Remediation requires a separate authenticated human approval.</p></div><ErrorNotice error={error} /><div className="form-actions"><button type="button" onClick={close}>Cancel</button><button className="primary" disabled={busy}><Play size={15} />{busy ? 'Starting…' : 'Start investigation'}</button></div></form></Modal>;
}

function RunList() {
  const { data, error, loading, reload } = useData<Data[]>('runs');
  return <><div className="page-heading"><div><h1>Agent workspace</h1><p className="subtitle">Follow real diagnostic calls, evidence and proposed actions.</p></div><Link href="/incidents"><button><Plus size={15} />Investigate an incident</button></Link></div><ErrorNotice error={error} retry={reload} />{loading ? <div className="skeleton" /> : <div className="card"><RunTable items={data || []} /></div>}</>;
}

function Audit({ report }: { report: Data }) {
  return <Card title="Audit timeline" extra={<span className="badge">Persisted events</span>}><div className="activity">{report.complete_audit_timeline?.map((event: Data, index: number) => <div className="activity-item" key={index}><div className="activity-icon">{event.source === 'gateway' ? <Terminal size={12} /> : <GitBranch size={12} />}</div><div className="activity-copy"><p>{human(event.kind || event.tool)} {event.outcome && <Badge value={event.outcome} />}</p><small>{date(event.at)} · {event.actor || event.source}</small>{event.detail && <details><summary className="mono muted" style={{ cursor: 'pointer', marginTop: 4 }}>Event details</summary><Json value={event.detail} /></details>}</div></div>)}</div>{report.timeline_truncated && <div className="notice warn">This view is truncated to 100 events per source. Use the backend CLI for the full audit export.</div>}</Card>;
}

function Workspace({ id }: { id: string }) {
  const { data, error, loading, reload } = useData(`runs/${id}`, 1500);
  const s = data?.snapshot; const report = data?.durable;
  const stages = [['triage', 'Triage'], ['investigation_planning', 'Planning'], ['readonly_mcp_execution', 'MCP evidence'], ['evidence_assessment', 'Assessment'], ['root_cause_proposal', 'Diagnosis'], ['remediation_planning', 'Remediation']];
  return <><Link href="/workspace" className="back"><ArrowLeft size={12} />All investigations</Link><div className="page-heading"><div><div className="inline"><h1>RUN-{short(id)}</h1>{data && <Badge value={data.status} />}</div><p className="subtitle">Incident investigation · {s?.request?.service_name || 'Loading target'}</p></div>{report && <Link href={`/approvals?run=${id}`}><button className="primary"><ShieldCheck size={15} />Review action</button></Link>}</div><ErrorNotice error={error} retry={reload} />{loading ? <div className="skeleton" /> : data && <>
    {s?.mode === 'fixture' && <div className="notice warn"><FlaskConical size={16} /><p><strong>Deterministic fixture run.</strong> Real LangGraph execution and MCP evidence; no LLM inference, tokens or API cost.</p></div>}
    {s && <Card title="Execution identity"><div className="card-pad"><Property label="Mode">{s.mode === 'real' ? 'Real model' : 'Deterministic fixture · no LLM inference'}</Property><Property label="Provider">{s.provider || 'Unavailable'}</Property><Property label="Model identifier">{s.model || 'Unavailable'}</Property><Property label="Estimated model API cost">{s.mode === 'fixture' ? 'N/A · no inference' : s.usage?.estimated_cost_usd == null ? 'Unavailable · no trusted pricing recorded' : `$${number(s.usage.estimated_cost_usd)}`}</Property></div></Card>}
    {data.error_code && <div className="notice error" role="alert"><CircleAlert size={16} />{human(data.error_code)}. Inspect the persisted timeline before retrying.</div>}
    {data.status === 'timed_out' && <div className="notice warn" role="status"><Clock3 size={16} />Investigation time budget exhausted. No remediation was authorized.</div>}
    <div className="card" style={{ marginBottom: 22 }}><div className="progress-rail">{stages.map(([key, title]) => <div className={`stage ${s?.transitions?.includes(key) ? 'done' : ''}`} key={key}><div className="stage-circle">{s?.transitions?.includes(key) ? <Check size={13} /> : <span>·</span>}</div>{title}</div>)}</div></div>
    <div className="stats"><Stat title="Diagnostic tool calls" value={s?.tool_call_history?.length ?? 0} foot={`Maximum ${s?.request?.max_tool_calls || 8} calls`} icon={Terminal} /><Stat title="Evidence references" value={s?.evidence_references?.length ?? 0} foot="Validated observations from MCP" icon={FileCheck2} /><Stat title="Investigation latency" value={number(s?.latency_ms, ' ms')} foot="Completed investigation wall-clock time" icon={Clock3} /><Stat title="Model tokens" value={s?.mode === 'fixture' ? 'N/A' : s?.usage?.usage_complete ? number((s.usage.input_tokens || 0) + (s.usage.output_tokens || 0)) : 'Unavailable'} foot={s?.mode === 'fixture' ? 'Fixture performs no model inference' : 'Provider-reported usage only'} icon={Bot} /></div>
    <div className="detail-grid"><div className="stack"><Card title="Read-only MCP tool calls" extra={<Badge value="bounded" />}>{s?.tool_call_history?.length ? <div className="table-wrap"><table><thead><tr><th>Tool</th><th>Target</th><th>Outcome</th><th>Latency</th><th>Evidence</th></tr></thead><tbody>{s.tool_call_history.map((call: Data, i: number) => <tr key={i}><td className="mono">{call.tool_name}</td><td>{call.arguments.service_name}</td><td><Badge value={call.outcome} /></td><td>{number(call.latency_ms, ' ms')}</td><td className="mono">{call.evidence_ref || '—'}</td></tr>)}</tbody></table></div> : <Empty>{data.status === 'queued' || data.status === 'running' ? 'Waiting for diagnostic evidence…' : 'No tool calls completed.'}</Empty>}</Card>
      <Card title="Evidence library"><div className="card-pad"><p className="subtitle">Operational data is untrusted. Fixture metadata and raw log instructions are excluded from agent context.</p>{s?.observations?.map((observation: Data) => <details className="evidence" key={observation.id}><summary><strong>{observation.id}</strong> · {observation.tool_name} <span className="mono muted"> / {short(observation.request_id)}</span></summary><Json value={observation.data} /></details>)}</div></Card>
      {report && <><Card title="Post-action verification"><div className="card-pad">{report.verification ? <><div className="inline"><Badge value={report.verification.outcome} /><span className="subtitle">Measured traffic after the committed action</span></div><Json value={report.verification} /></> : <p className="muted">No post-action verification has been recorded.</p>}</div></Card><Audit report={report} /></>}
    </div><div className="stack"><Card title="Candidate root cause"><div className="card-pad">{s?.candidate_root_cause ? <><h3>{s.candidate_root_cause.summary || s.candidate_root_cause.cause || s.candidate_root_cause.category}</h3><Json value={s.candidate_root_cause} /></> : <p className="muted">No supported root cause proposed.</p>}<Property label="Confidence">{percent(s?.confidence)}</Property>{s?.uncertainty?.map((text: string, i: number) => <p key={i} className="subtitle" style={{ marginTop: 10 }}>{text}</p>)}</div></Card><Card title="Alternative hypotheses"><div className="card-pad">{s?.current_hypotheses?.length ? s.current_hypotheses.map((h: Data, i: number) => <div className="hypothesis" key={i}><Json value={h} /></div>) : <p className="muted">No hypotheses recorded yet.</p>}</div></Card><Card title="Proposed remediation"><div className="card-pad">{s?.proposed_remediation ? <><Badge value="proposal only" /><Json value={s.proposed_remediation} />{report && <Link href={`/approvals?run=${id}`}><button style={{ width: '100%' }}><ShieldCheck size={14} />Open human review</button></Link>}</> : <p className="muted">No remediation proposed.</p>}</div></Card>{s?.errors?.length > 0 && <Card title="Run errors"><div className="card-pad"><Json value={s.errors} /></div></Card>}</div></div>
    </>}</>;
}

function Approvals({ meta, login }: { meta: Data | null; login: () => void }) {
  const { data, error, loading, reload } = useData<Data[]>('approvals', 1800);
  const [selected, setSelected] = useState(''); const [decision, setDecision] = useState<'approve' | 'reject' | null>(null);
  const [checked, setChecked] = useState(false); const [busy, setBusy] = useState(false); const [operationError, setOperationError] = useState('');
  useEffect(() => { const requested = new URLSearchParams(window.location.search).get('run'); if (requested) setSelected(requested); }, []);
  const report = data?.find(item => item.run_id === selected) || data?.find(item => item.approval.state === 'pending') || data?.[0];
  const approval = report?.approval;
  const openDecision = (value: 'approve' | 'reject') => { if (!meta?.session) return login(); setChecked(false); setOperationError(''); setDecision(value); };
  return <><div className="page-heading"><div><h1>Approval center</h1><p className="subtitle">Review exact actions. Authorize deliberately. Verify the result.</p></div><span className="badge"><ShieldCheck size={12} />Human authority required</span></div><ErrorNotice error={error} retry={reload} /><ErrorNotice error={operationError} />
    {!meta?.actions_enabled && <div className="notice warn"><ShieldCheck size={16} /><p>Sandbox action execution is disabled by backend policy. Review remains available. An operator must explicitly enable the server-side action flag to execute.</p></div>}
    {loading ? <div className="skeleton" /> : !report ? <div className="card"><Empty>No remediation requests. Complete an actionable investigation first.</Empty></div> : <div className="approval-layout"><div className="approval-list">{data?.map(item => <button key={item.run_id} className={`approval-option ${report.run_id === item.run_id ? 'selected' : ''}`} onClick={() => { setSelected(item.run_id); setOperationError(''); }}><div className="inline" style={{ justifyContent: 'space-between' }}><span className="mono">RUN-{short(item.run_id)}</span><Badge value={item.approval.state} /></div><strong>{human(item.approval.tool)}</strong><p className="subtitle">{item.approval.service_name}</p><small>Expires {date(item.approval.expires_at)}</small></button>)}</div><div className="stack"><Card title="Action review" extra={<Badge value={approval.state} />}><div className="card-pad"><div className="inline" style={{ justifyContent: 'space-between', marginBottom: 14 }}><h3 style={{ fontSize: 16 }}>{human(approval.tool)}</h3><Badge value={approval.risk} /></div><Property label="Target resource">{approval.service_name}</Property><Property label="Run ID"><Link href={`/workspace/${report.run_id}`} className="mono">{report.run_id}</Link></Property><Property label="Incident"><Link href={`/incidents/${report.incident_id}`} className="mono">{report.incident_id}</Link></Property><Property label="Expires at">{date(approval.expires_at)}</Property><Property label="Approved by">{approval.approved_by || 'No approval issued'}</Property><h3 style={{ marginTop: 22 }}>Exact approved arguments</h3><Json value={approval.arguments} /><h3>Immutable action fingerprint</h3><div className="fingerprint">{approval.fingerprint}</div><h3>Supporting evidence</h3><Json value={approval.evidence} /><h3>Verification policy</h3><Json value={approval.verification_plan} /><div className="notice"><ShieldCheck size={16} /><p>This approval is bound to this run, target and exact arguments. The backend revalidates expiry, permissions and live resource preconditions before execution.</p></div><div className="inline" style={{ justifyContent: 'flex-end' }}>{approval.state === 'pending' && <><button className="danger" onClick={() => openDecision('reject')}><X size={14} />Reject action</button><button className="primary" onClick={() => openDecision('approve')}><ShieldCheck size={14} />Approve action</button></>}{approval.state === 'approved' && <><button className="danger" onClick={() => openDecision('reject')}>Revoke approval</button><button className="primary" disabled={busy || !meta?.actions_enabled} onClick={async () => { if (!meta?.session) return login(); setBusy(true); setOperationError(''); try { await api(`runs/${report.run_id}/resume`, 'POST'); await reload(); } catch (e) { setOperationError((e as Error).message); } finally { setBusy(false); } }}><Play size={14} />Execute approved action</button></>}{approval.state === 'consumed' && <Link href={`/workspace/${report.run_id}`}><button><CheckCheck size={15} />Inspect verification</button></Link>}</div></div></Card>{report.verification && <Card title="Recovery verification"><div className="card-pad"><Badge value={report.verification.outcome} /><Json value={report.verification} /></div></Card>}<Audit report={report} /></div></div>}
    {decision && approval && <Modal title={decision === 'approve' ? 'Approve this exact sandbox action' : 'Reject this action'} close={() => setDecision(null)}><p className="subtitle">{approval.tool} → {approval.service_name}</p><Json value={approval.arguments} /><div className="fingerprint">{approval.fingerprint}</div><label className="check"><input type="checkbox" checked={checked} onChange={e => setChecked(e.target.checked)} />I reviewed the exact target, arguments, supporting evidence and risk. Record my authenticated human decision.</label><ErrorNotice error={operationError} /><div className="form-actions"><button onClick={() => setDecision(null)}>Cancel</button><button className={decision === 'approve' ? 'primary' : 'danger'} disabled={!checked || busy} onClick={async () => { setBusy(true); setOperationError(''); try { await api(`approvals/${approval.id}/decision`, 'POST', { decision, fingerprint: approval.fingerprint }); setDecision(null); await reload(); } catch (e) { setOperationError((e as Error).message); } finally { setBusy(false); } }}>{busy ? 'Recording…' : decision === 'approve' ? 'Confirm approval' : 'Confirm rejection'}</button></div></Modal>}
  </>;
}

function Evaluations() {
  const { data, error, loading, reload } = useData('evaluations', 60000); const [split, setSplit] = useState('held-out');
  const report = data?.reports[split]; const baseline = report?.metrics?.baseline;
  return <><div className="page-heading"><div><h1>Evaluation intelligence</h1><p className="subtitle">Measured outcomes, visible safety gates and honest comparisons.</p></div>{data && <Badge value={data.release.release_ready ? 'pass' : 'blocked'} />}</div><ErrorNotice error={error} retry={reload} />{loading ? <div className="skeleton" /> : data && <>
    <div className="notice"><FlaskConical size={16} /><p><strong>Recorded Stage 5 benchmark · dataset v{report?.dataset_version}.</strong> Completed {date(report?.finished_at)}. These are historical measurements, not a new measurement of this release. No real model was configured for these reports.</p></div><div className="tabs">{['calibration', 'development', 'held-out'].map(item => <button key={item} className={split === item ? 'active' : ''} onClick={() => setSplit(item)}>{human(item)}</button>)}</div>
    <div className="stats"><Stat title="Baseline task success" value={percent(baseline?.task_completion?.value)} foot={`${baseline?.task_completion?.numerator}/${baseline?.task_completion?.denominator} attempted cases`} icon={CheckCheck} /><Stat title="Unsupported diagnoses" value={percent(baseline?.unsupported_diagnosis_rate?.value)} foot={`${baseline?.unsupported_diagnosis_rate?.numerator}/${baseline?.unsupported_diagnosis_rate?.denominator} emitted diagnoses`} icon={TriangleAlert} /><Stat title="End-to-end p95" value={number(baseline?.latency_ms?.p95, ' ms')} foot={`${baseline?.latency_ms?.denominator} measured baseline cases`} icon={Clock3} /><Stat title="Baseline API cost" value={baseline?.estimated_api_cost_usd?.total == null ? 'Unavailable' : `$${baseline.estimated_api_cost_usd.total.toFixed(2)}`} foot="Rules make no paid model calls" icon={Bot} /></div>
    <div className="two-col"><Card title="Matched benchmark comparison"><div className="table-wrap"><table><thead><tr><th>Version / arm</th><th>Attempted</th><th>Success</th><th>P95 latency</th><th>Model cost</th></tr></thead><tbody>{Object.entries(report?.metrics || {}).map(([arm, raw]) => { const value = raw as Data; return <tr key={arm}><td>{arm === 'baseline' ? 'A · Deterministic rules' : arm === 'llm' ? 'B · LLM + tools' : 'C · Planning + verification'}</td><td>{value.attempted} / {value.selected}</td><td>{percent(value.task_completion?.value)}</td><td>{number(value.latency_ms?.p95, ' ms')}</td><td>{value.estimated_api_cost_usd?.total == null ? 'Unavailable' : `$${value.estimated_api_cost_usd.total.toFixed(2)}`}</td></tr>; })}</tbody></table></div><div className="card-pad"><p className="subtitle">Unavailable model arms are excluded, not scored as zero success. No agent superiority has been measured.</p><Property label="Root-cause accuracy">{percent(baseline?.root_cause_accuracy?.value)} · {baseline?.root_cause_accuracy?.numerator}/{baseline?.root_cause_accuracy?.denominator}</Property><Property label="95% Wilson interval">{baseline?.root_cause_accuracy?.wilson_95?.map((v: number) => percent(v)).join(' – ') || 'Unavailable'}</Property><Property label="Abstentions / timeouts">{baseline?.abstentions} / {baseline?.timeouts}</Property><Property label="Diagnostic calls / incident">{baseline?.diagnostic_tool_calls?.mean}</Property><Property label="Unauthorized action attempts">{baseline?.unauthorized_action_attempts?.count} / {baseline?.unauthorized_action_attempts?.diagnostic_call_denominator} calls</Property><Property label="Version comparison">{data.version_comparison}</Property></div></Card><Card title="Release gates · deterministic baseline"><div className="card-pad">{report?.gates?.baseline?.map((gate: Data) => <div className="gate" key={gate.name}><div>{human(gate.name)}<small>{gate.requirement}</small></div><Badge value={gate.status} /></div>)}</div></Card></div><Card title="Operational safety and recovery evidence"><div className="card-pad"><p className="subtitle">Separate Stage 5 operational probes. Diagnostic benchmark cases do not imply approved action or recovery coverage.</p><Json value={data.operations} /></div></Card>
    </>}</>;
}

const workflowNodes: Node[] = [
  { id: 'triage', position: { x: 0, y: 50 }, data: { label: '01 · Incident triage' } },
  { id: 'plan', position: { x: 210, y: 50 }, data: { label: '02 · Investigation plan' } },
  { id: 'mcp', position: { x: 420, y: 50 }, data: { label: '03 · Read-only MCP' } },
  { id: 'assess', position: { x: 630, y: 50 }, data: { label: '04 · Assess evidence' } },
  { id: 'proposal', position: { x: 630, y: 180 }, data: { label: '05 · Propose remediation' } },
  { id: 'human', position: { x: 420, y: 180 }, data: { label: '06 · Human approval' } },
  { id: 'execute', position: { x: 210, y: 180 }, data: { label: '07 · Sandbox execution' } },
  { id: 'verify', position: { x: 0, y: 180 }, data: { label: '08 · Verify recovery' } },
  { id: 'abstain', position: { x: 840, y: 50 }, data: { label: 'Abstain / budget limit' } },
];
const workflowEdges = [['triage', 'plan'], ['plan', 'mcp'], ['mcp', 'assess'], ['assess', 'plan'], ['assess', 'proposal'], ['assess', 'abstain'], ['proposal', 'human'], ['human', 'execute'], ['execute', 'verify']].map(([source, target]) => ({ id: `${source}-${target}`, source, target, markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: '#93baa9' }, label: source === 'assess' && target === 'plan' ? 'more evidence' : source === 'human' ? 'exact signed grant' : undefined }));
const nodeDetails: Record<string, string> = {
  triage: 'Loads incident evidence through MCP. The agent prompt receives no privileged scenario metadata.',
  plan: 'Selects a typed read-only diagnostic within the tool, model-call and wall-clock budgets.',
  mcp: 'Uses the real MCP protocol and scoped credentials. Observations are positively projected and untrusted.',
  assess: 'Checks citations and compares alternatives. Conditional routing requests more evidence or abstains.',
  proposal: 'Proposes an action and target. The recommendation does not carry execution authority.',
  human: 'An authenticated human reviews the exact arguments, resource, risk and immutable fingerprint.',
  execute: 'Revalidates the signed grant and preconditions. PostgreSQL action records and idempotency protect effects.',
  verify: 'Generates measured traffic after the action. Records verified, failed or inconclusive recovery.',
  abstain: 'Insufficient, unsupported or exhausted investigation returns uncertainty without action authority.',
};
function Architecture() {
  const { data, error, loading, reload } = useData('architecture', 60000); const [selected, setSelected] = useState('human');
  return <><div className="page-heading"><div><h1>System architecture</h1><p className="subtitle">A bounded investigator. A separate approval authority. A verifiable result.</p></div><span className="badge"><Workflow size={12} />Implementation map</span></div><ErrorNotice error={error} retry={reload} /><div className="detail-grid" style={{ marginBottom: 24 }}><Card title="Agent lifecycle" extra={<span className="muted" style={{ fontSize: 10 }}>Pan · zoom · select a node</span>}><div className="workflow"><ReactFlow nodes={workflowNodes} edges={workflowEdges} fitView nodesDraggable={false} onNodeClick={(_, node) => setSelected(node.id)} minZoom={.35} maxZoom={1.5} aria-label="Agent workflow architecture"><Background gap={20} size={1} color="#dce7e2" /><Controls showInteractive={false} /></ReactFlow></div></Card><Card title={String(workflowNodes.find(n => n.id === selected)?.data.label)}><div className="card-pad"><p className="subtitle">{nodeDetails[selected]}</p><Property label="Persistence">PostgreSQL + durable LangGraph checkpoints</Property><Property label="Action authority">Authenticated human + signed exact grant</Property><Property label="Environment">Local fictional service simulator</Property><Property label="Network boundary">Browser → Next.js BFF → local API</Property><div className="notice" style={{ margin: '20px 0 0' }}><ShieldCheck size={16} /><p>This diagram describes implemented routing. It does not animate fabricated live execution.</p></div></div></Card></div>{loading ? <div className="skeleton" /> : data && <><Card title="Service dependencies"><div className="card-pad inline" style={{ justifyContent: 'center', padding: 28 }}><span className="badge"><Server size={14} />checkout-service</span><ArrowRight size={16} /><div className="stack" style={{ gap: 8 }}>{data.dependencies['checkout-service'].map((service: string) => <span className="badge" key={service}><Database size={14} />{service}</span>)}</div><span className="muted" style={{ marginLeft: 30, fontSize: 11 }}>Observed via get_dependency_status</span></div></Card><div className="section-head" style={{ marginTop: 28 }}><h2>MCP tool inventory</h2><span className="eyebrow" style={{ fontSize: 9 }}>{data.tools.length} allowlisted tools</span></div><div className="tool-grid">{data.tools.map((tool: Data) => <article className="tool-card" key={tool.name}><div className="inline"><Terminal size={14} color="#86a497" /><Badge value={tool.access} /></div><code>{tool.name}</code><p className="subtitle" style={{ fontSize: 10 }}>{tool.access === 'read-only' ? 'Available to the scoped investigator' : 'Available only to the separate durable execution path'}</p></article>)}</div></>}</>;
}
