import { useEffect, useRef, useState } from 'react'
import './App.css'

type Result = { question: string; sql: string; model: string; validated: boolean; executed: boolean; columns?: string[]; rows?: unknown[][]; row_count?: number; explanation?: string; cache_hit?: boolean; repair_count?: number; total_duration_ms?: number; database_duration_ms?: number; estimated_cost?: number; schema_version?: string; result_generated_at?: string; requestId?: string | null; audit?: string | null }
type Entry = { id: number; question: string; result: Result }
const suggestions = ['Show me the top 10 customers by total spending', 'How many orders have been placed?', 'What is the average order value?']
const display = (value: unknown): string => value == null ? 'NULL' : typeof value === 'object' ? JSON.stringify(value) : String(value)
async function request(path: string, init?: RequestInit) {
  const response = await fetch(`/api${path}`, init)
  const data = await response.json().catch(() => null)
  if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `Request failed (${response.status}). Check the backend connection and try again.`)
  if (!data) throw new Error('The API returned an empty response.')
  return { data, response }
}
function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, string> = { shield: 'M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6l-8-3Z M8 12l3 3 5-6', grid: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z', clock: 'M12 8v5l3 2 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0', arrow: 'M5 12h14 M13 6l6 6-6 6', spark: 'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z', database: 'M20 6c0 2-4 3-8 3S4 8 4 6s4-3 8-3 8 1 8 3Z M4 6v12c0 2 4 3 8 3s8-1 8-3V6 M4 12c0 2 4 3 8 3s8-1 8-3', code: 'm8 7-5 5 5 5 M16 7l5 5-5 5 M14 4l-4 16', download: 'M12 3v12 m-5-5 5 5 5-5 M4 16v5h16v-5', plus: 'M12 5v14 M5 12h14', check: 'm5 12 4 4L19 6' }
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] || paths.grid} /></svg>
}
function App() {
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState<Result | null>(null)
  const [history, setHistory] = useState<Entry[]>([])
  const [page, setPage] = useState<'workspace' | 'history'>('workspace')
  const [tab, setTab] = useState<'results' | 'sql' | 'details'>('results')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [lastMode, setLastMode] = useState<'query' | 'generate-sql'>('query')
  const [connection, setConnection] = useState('Checking connection')
  const [ready, setReady] = useState(false)
  const [filter, setFilter] = useState('')
  const [offset, setOffset] = useState(0)
  const input = useRef<HTMLTextAreaElement>(null)
  const inFlight = useRef(false)
  useEffect(() => {
    let active = true
    async function check() {
      try { await request('/health', { signal: AbortSignal.timeout(8000) }); await request('/ready', { signal: AbortSignal.timeout(8000) }); if (active) { setReady(true); setConnection('Database connected') } }
      catch (e) { if (active) { setReady(false); setConnection(e instanceof Error && e.message.includes('Database') ? 'Database unavailable' : 'Connection unavailable') } }
    }
    void check(); const timer = setInterval(check, 30000)
    return () => { active = false; clearInterval(timer) }
  }, [])
  async function run(mode: 'query' | 'generate-sql') {
    if (inFlight.current || question.trim().length < 3) return
    inFlight.current = true; setLastMode(mode); setBusy(true); setError(''); setNotice(''); setResult(null)
    try {
      const { data, response } = await request(`/${mode}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: question.trim() }) })
      const next: Result = { ...data, requestId: response.headers.get('X-Request-ID'), audit: response.headers.get('X-Audit-Status') }
      setResult(next); setTab(mode === 'query' ? 'results' : 'sql'); setFilter(''); setOffset(0)
      setHistory(items => [{ id: Date.now(), question: next.question, result: next }, ...items].slice(0, 50))
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to complete your request.') }
    finally { inFlight.current = false; setBusy(false) }
  }
  function reset() { setPage('workspace'); setQuestion(''); setResult(null); setError(''); setNotice(''); input.current?.focus() }
  function restore(entry: Entry) { setQuestion(entry.question); setResult(entry.result); setPage('workspace'); setTab(entry.result.rows ? 'results' : 'sql'); setError(''); setNotice(''); setFilter(''); setOffset(0) }
  function download() {
    if (!result?.columns || !result.rows) return
    const cell = (v: unknown) => { let text = display(v); if (/^[=+@\-\t\r]/.test(text)) text = `'${text}`; return `"${text.replaceAll('"', '""')}"` }
    const csv = [result.columns, ...result.rows].map(row => row.map(cell).join(',')).join('\r\n')
    const url = URL.createObjectURL(new Blob(['\uFEFF', csv], { type: 'text/csv;charset=utf-8;' })); const link = document.createElement('a'); link.href = url; link.download = 'schemaguard-results.csv'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  const rows = (result?.rows || []).filter(row => row.some(value => display(value).toLowerCase().includes(filter.toLowerCase())))
  return <div className="shell">
    <aside className="sidebar">
      <a className="brand" href="#" onClick={e => { e.preventDefault(); if (!busy) reset() }}><span className="brand-mark"><Icon name="shield" size={25} /></span><span>SchemaGuard<span className="brand-sub">SQL WORKSPACE</span></span></a>
      <div className="workspace-label">WORKSPACE <span>01</span></div>
      <nav aria-label="Main navigation"><button className={page === 'workspace' ? 'nav active' : 'nav'} onClick={() => setPage('workspace')}><Icon name="grid" /> Query workspace <span>↗</span></button><button className={page === 'history' ? 'nav active' : 'nav'} onClick={() => setPage('history')}><Icon name="clock" /> Session history <small>{history.length}</small></button></nav>
      <div className="recent"><div className="workspace-label">RECENT QUERIES</div>{history.length ? history.slice(0, 5).map(entry => <button disabled={busy} key={entry.id} onClick={() => restore(entry)}><Icon name="code" size={15} /><span>{entry.question}</span></button>) : <p>Your questions will appear here.</p>}</div>
      <div className="sidebar-bottom"><div className="private-card"><Icon name="shield" /><strong>Your data stays yours.</strong><p>Private analysis. Read-only queries.<br />Built with guardrails.</p></div><div className="profile"><span className="avatar">SG</span><div>Local workspace<small>Private environment</small></div><span className="status-dot" /></div></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div>Workspace <span>/</span> <strong>{page === 'workspace' ? 'Query studio' : 'Session history'}</strong></div><span className={`connection ${ready ? 'online' : ''}`}><span className="status-dot" />{connection}</span></header>
    <main><div className="page-heading"><div><div className="eyebrow">YOUR DATA, IN PLAIN ENGLISH</div><h1>{page === 'workspace' ? 'A little curiosity. A lot of insight.' : 'Pick up where you left off.'}</h1><p>{page === 'workspace' ? 'Ask a question. Get trusted SQL and answers from your database.' : 'Revisit the questions and results from this session.'}</p></div><button className="secondary new-query" disabled={busy} onClick={reset}><Icon name="plus" size={17} /> New query</button></div>
    {page === 'history' ? <section className="panel history-panel"><div className="panel-heading"><h2>Session history</h2><span className="muted">{history.length} queries · kept in memory</span></div>{history.length ? history.map(entry => <button className="history-row" disabled={busy} key={entry.id} onClick={() => restore(entry)}><Icon name="clock" /><span>{entry.question}<small>{new Date(entry.id).toLocaleTimeString()} · {entry.result.rows ? `${entry.result.row_count} rows` : 'SQL generated'}</small></span><Icon name="arrow" /></button>) : <div className="empty"><Icon name="clock" size={32} /><h3>A fresh start</h3><p>Your completed queries will appear here.</p><button className="secondary" onClick={reset}>Ask your first question</button></div>}</section> : <>
    <section className="panel composer"><div className="panel-heading"><h2><span className="icon-tile"><Icon name="spark" /></span> Ask your database</h2><span className="pill"><Icon name="shield" size={13} /> Read-only by design</span></div><form onSubmit={e => { e.preventDefault(); void run('query') }}><label className="sr-only" htmlFor="question">Your database question</label><textarea id="question" ref={input} disabled={busy} maxLength={1000} value={question} onChange={e => setQuestion(e.target.value)} placeholder="What would you like to know about your data?" onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); void run('query') } }} /><div className="composer-actions"><span className="input-hint">Natural language in. Insights out. <small>{question.length}/1000</small></span><div><button className="secondary" type="button" disabled={busy || question.trim().length < 3} onClick={() => void run('generate-sql')}><Icon name="code" size={16} /> Generate SQL</button><button className="primary" disabled={busy || question.trim().length < 3} type="submit">{busy ? 'Working…' : 'Run query'}<Icon name="arrow" size={17} /></button></div></div></form><div className="suggestions"><span>TRY ASKING</span>{suggestions.map((item, i) => <button disabled={busy} key={item} onClick={() => { setQuestion(item); input.current?.focus() }}>{['Top customers', 'Total orders', 'Average order value'][i]} <span>↗</span></button>)}</div></section>
    <div className="workflow"><span><Icon name="spark" size={16} /> Natural language</span><i>→</i><span><Icon name="code" size={16} /> SQL generation</span><i>→</i><span><Icon name="shield" size={16} /> Safety validation</span><i>→</i><span><Icon name="database" size={16} /> Your results</span></div>
    {error && <div className="error" role="alert"><strong>We couldn’t complete this query.</strong><p>{error}</p><button className="secondary" onClick={() => void run(lastMode)}>Try again</button></div>}
    <section className="panel result-panel" aria-busy={busy}><div className="panel-heading result-heading"><div className="tabs" role="tablist" aria-label="Query output">{(['results', 'sql', 'details'] as const).map(value => <button id={`tab-${value}`} role="tab" aria-selected={tab === value} aria-controls="output-panel" key={value} onClick={() => setTab(value)} className={tab === value ? 'selected' : ''}>{value === 'results' ? 'Results' : value === 'sql' ? 'Generated SQL' : 'Query details'}{value === 'results' && result?.row_count !== undefined && <small>{result.row_count}</small>}</button>)}</div>{result?.rows && <button className="text-button" onClick={download}><Icon name="download" size={16} /> Export CSV</button>}</div><div id="output-panel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
    {busy ? <div className="empty" role="status"><div className="spinner" /><h3>Turning your question into insight</h3><p>The backend is generating and validating your SQL.<br />Local models may take a moment.</p></div> : !result ? <div className="empty"><div className="empty-art"><span /><Icon name="database" size={36} /><span /></div><h3>Your next insight starts with a question.</h3><p>Explore your data without writing a line of SQL.<br />Your results will appear right here.</p><div className="empty-foot"><Icon name="shield" size={14} /> Validated SQL <b>·</b> Read-only access <b>·</b> Private by default</div></div> : tab === 'sql' ? <div className="sql-view"><div><span className="pill">{result.validated ? '✓ Validated' : 'Not validated'}</span><button className="text-button" onClick={async () => { try { await navigator.clipboard.writeText(result.sql); setNotice('SQL copied to clipboard.') } catch { setNotice('Copy unavailable. Select the SQL to copy it manually.') } }}>Copy SQL</button></div><pre><code>{result.sql}</code></pre><p className="muted">{result.executed ? 'Executed by the backend.' : result.cache_hit ? 'Results served from the backend cache.' : 'Generated and validated only. No query was executed.'}</p></div> : tab === 'details' ? <div className="details">{Object.entries({ Model: result.model, 'Execution': result.cache_hit ? 'Cached result' : result.executed ? 'Executed' : 'Not executed', 'Total duration': result.total_duration_ms == null ? '—' : `${result.total_duration_ms} ms`, 'Database duration': result.database_duration_ms == null ? '—' : `${result.database_duration_ms} ms`, 'Repair attempts': result.repair_count ?? '—', 'Estimated cost': result.estimated_cost ?? '—', 'Audit status': result.audit ?? 'Not provided', 'Request ID': result.requestId ?? 'Not provided', 'Schema version': result.schema_version ?? '—', 'Result generated': result.result_generated_at ? new Date(result.result_generated_at).toLocaleString() : '—' }).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</div> : result.rows ? <><div className="result-summary"><span><Icon name="check" size={17} />{result.cache_hit ? 'Retrieved from cache' : 'Query completed'}<small>{result.total_duration_ms?.toLocaleString()} ms</small></span><input aria-label="Filter results" placeholder="Filter results…" value={filter} onChange={e => { setFilter(e.target.value); setOffset(0) }} /></div>{result.explanation && <p className="explanation">{result.explanation}</p>}<div className="table-wrap"><table><thead><tr><th>#</th>{result.columns?.map((column, i) => <th key={i}>{column}</th>)}</tr></thead><tbody>{rows.slice(offset, offset + 25).map((row, i) => <tr key={offset + i}><td>{offset + i + 1}</td>{row.map((value, j) => <td key={j} className={value == null ? 'null' : ''}>{display(value)}</td>)}</tr>)}</tbody></table>{!rows.length && <p className="no-rows">{filter ? 'No rows match your filter.' : 'This query returned no rows.'}</p>}</div><div className="table-footer"><span>{rows.length ? `${offset + 1}–${Math.min(offset + 25, rows.length)} of ${rows.length}` : '0'} rows</span><div><button className="secondary" disabled={offset === 0} onClick={() => setOffset(offset - 25)}>Previous</button><button className="secondary" disabled={offset + 25 >= rows.length} onClick={() => setOffset(offset + 25)}>Next</button></div></div></> : <div className="empty"><Icon name="code" size={32} /><h3>Your SQL is ready</h3><p>View the Generated SQL tab, or run your question to retrieve results.</p><button className="primary" onClick={() => void run('query')}>Run query <Icon name="arrow" size={16} /></button></div>}
    </div></section><p role="status" className="notice">{notice}</p></>}
    <footer><span><Icon name="shield" size={14} /> SchemaGuard SQL</span><span>A safer way to explore your data.</span></footer></main></div>
  </div>
}
export default App

