import React, { createContext, useContext, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Link, Navigate, Outlet, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom';
import { api, downloadReport } from './api';
import './styles.css';

const Auth = createContext(null);
const useAuth = () => useContext(Auth); // #this is function definition
const message = (error) => error instanceof Error ? error.message : 'Something went wrong.';

// this a component that provides authentication context to its children. It manages the user state and provides a refresh function to fetch the current user data from the API.
function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined);   // hook to manage user state, initially undefined. setUser is a function to update the user state.
  const refresh = () => api('/auth/me/').then(setUser).catch(() => setUser(null));
  useEffect(() => { refresh(); }, []); //useEffect hook to call refresh function on component mount, which fetches the current user data from the API and updates the user state.
  return <Auth.Provider value={{ user, setUser, refresh }}>{children}</Auth.Provider>;
}

// Protected component checks if the user is authenticated. If the user is undefined, it shows a loading message. If the user is authenticated, it renders the Shell component with the Outlet for nested routes. If the user is not authenticated, it redirects to the login page.
// it is called in the RoutesRoot component to protect certain routes that require authentication.
function Protected() {
  const { user } = useAuth();
  const location = useLocation();
  if (user === undefined) return <div className="loading">Loading your workspace…</div>;
  return user ? <Shell><Outlet /></Shell> : <Navigate to="/login" replace state={{ from: location.pathname }} />;
}

function Shell({ children }) {
  const { user, setUser } = useAuth();// useAuth hook to access the user state and setUser function from the Auth context.
  const navigate = useNavigate(); // useNavigate hook to programmatically navigate to different routes.
  const location = useLocation(); // useLocation hook to access the current location object, which contains information about the current URL.
  const signOut = async () => { try { await api('/auth/logout/', { method: 'POST' }); } finally { setUser(null); navigate('/login'); } };
  return <div className="app-shell">
    <aside className="sidebar">
      <Link to="/inventions" className="brand"><span className="brand-mark">P</span><span>Patent<span className="brand-light">Desk</span></span></Link>
      <div className="workspace-label">WORKSPACE</div>
      <div className="org-chip"><span className="org-dot" />{user?.organization?.name}</div>
      <nav className="nav-links">
        <Link className={location.pathname.startsWith('/inventions') ? 'active' : ''} to="/inventions"><span>▤</span> My inventions</Link>
        <Link className={location.pathname === '/customers/new' ? 'active' : ''} to="/customers/new"><span>＋</span> Add customer</Link>
        <Link className={location.pathname === '/help' ? 'active' : ''} to="/help"><span>?</span> Help</Link>
      </nav>
      <div className="sidebar-bottom"><div className="avatar">{user?.username?.slice(0, 1).toUpperCase()}</div><div className="user-meta"><b>{user?.username}</b><small>{user?.email || 'Workspace member'}</small></div><button className="icon-button" aria-label="Sign out" title="Sign out" onClick={signOut}>↗</button></div>
    </aside>
    <main className="main"><header className="topbar"><span className="breadcrumb">Patent analysis <span>/</span> {location.pathname.includes('new') ? 'New' : location.pathname.includes('help') ? 'Help' : 'Workspace'}</span><span className="secure-label"><i /> Secure workspace</span></header>{children}</main>
  </div>;
}

function PageTitle({ eyebrow, title, description, action }) { return <div className="page-title"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1>{description && <p>{description}</p>}</div>{action}</div>; }
function Notice({ error, success }) { return <>{error && <div className="notice error">{error}</div>}{success && <div className="notice success">{success}</div>}</>; }
function Empty({ title, body, action }) { return <div className="empty"><div className="empty-icon">◇</div><h3>{title}</h3><p>{body}</p>{action}</div>; }

function Login() {
  const { user, setUser } = useAuth(); const navigate = useNavigate(); const location = useLocation();
  const [username, setUsername] = useState(''); const [password, setPassword] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/inventions" replace />;
  const submit = async (event) => { event.preventDefault(); setBusy(true); setError(''); try { setUser(await api('/auth/login/', { method: 'POST', body: JSON.stringify({ username, password }) })); navigate(location.state?.from || '/inventions', { replace: true }); } catch (e) { setError(message(e)); } finally { setBusy(false); } };
  return <AuthFrame><div className="auth-card"><div className="auth-icon">P</div><div className="eyebrow">WELCOME BACK</div><h1>Sign in to your workspace</h1><p className="muted">Use the account provided by your organization administrator.</p><Notice error={error} /><form onSubmit={submit} className="form"><label>Username<input autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required autoFocus /></label><label>Password<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></label><button className="button primary full" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'} <span>→</span></button></form><Link className="auth-link" to="/forgot-password">Forgot password?</Link></div><div className="auth-foot">PatentDesk · Private organization portal</div></AuthFrame>;
}

function AuthFrame({ children }) { return <div className="auth-page"><div className="auth-brand"><span className="brand-mark">P</span> Patent<span className="brand-light">Desk</span></div>{children}</div>; }

function ForgotPassword() {
  const [email, setEmail] = useState(''); const [done, setDone] = useState(false); const [error, setError] = useState('');
  const submit = async e => { e.preventDefault(); setError(''); try { await api('/auth/password-reset/', { method: 'POST', body: JSON.stringify({ email }) }); setDone(true); } catch (err) { setError(message(err)); } };
  return <AuthFrame><div className="auth-card"><div className="eyebrow">ACCOUNT RECOVERY</div><h1>Reset your password</h1><p className="muted">Enter your account email and we’ll send a reset link if it’s registered.</p><Notice error={error} success={done ? 'If that email belongs to an account, a reset link has been sent.' : ''} />{!done && <form onSubmit={submit} className="form"><label>Email<input type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} required /></label><button className="button primary full">Send reset link</button></form>}<Link className="auth-link" to="/login">← Back to sign in</Link></div></AuthFrame>;
}

function ResetPassword() {
  const { uid, token } = useParams(); const navigate = useNavigate(); const [password, setPassword] = useState(''); const [confirmation, setConfirmation] = useState(''); const [error, setError] = useState('');
  const submit = async e => { e.preventDefault(); setError(''); try { const result = await api('/auth/password-reset/confirm/', { method: 'POST', body: JSON.stringify({ uid, token, password, password_confirmation: confirmation }) }); navigate('/login', { state: { notice: result.detail } }); } catch (err) { setError(message(err)); } };
  return <AuthFrame><div className="auth-card"><div className="eyebrow">ACCOUNT RECOVERY</div><h1>Choose a new password</h1><Notice error={error} /><form onSubmit={submit} className="form"><label>New password<input type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} required /></label><label>Confirm password<input type="password" autoComplete="new-password" value={confirmation} onChange={e => setConfirmation(e.target.value)} required /></label><button className="button primary full">Update password</button></form></div></AuthFrame>;
}

function Inventions() {
  const [customers, setCustomers] = useState([]); const [selected, setSelected] = useState(''); const [inventions, setInventions] = useState([]); const [loading, setLoading] = useState(true); const [error, setError] = useState('');
  useEffect(() => { api('/customers/').then(data => { setCustomers(data.customers); if (data.customers.length) setSelected(String(data.customers[0].id)); }).catch(e => setError(message(e))).finally(() => setLoading(false)); }, []);
  useEffect(() => { if (!selected) { setInventions([]); return; } api(`/inventions/?customer_id=${encodeURIComponent(selected)}`).then(data => setInventions(data.inventions)).catch(e => setError(message(e))); }, [selected]);
  return <div className="content"><PageTitle eyebrow="YOUR WORKSPACE" title="My inventions" description="Review invention disclosures and their analysis history." action={<Link className="button primary" to="/inventions/new">＋ New invention</Link>} />
    <Notice error={error} />
    {loading ? <div className="loading">Loading customers…</div> : !customers.length ? <Empty title="Start with a customer" body="Add a customer to organize invention disclosures for your organization." action={<Link className="button primary" to="/customers/new">＋ Add customer</Link>} /> : <>
      <div className="filter-row"><label htmlFor="customer-select">Customer</label><select id="customer-select" value={selected} onChange={e => setSelected(e.target.value)}>{customers.map(customer => <option key={customer.id} value={customer.id}>{customer.name}</option>)}</select><span className="count-label">{inventions.length} {inventions.length === 1 ? 'invention' : 'inventions'}</span></div>
      {inventions.length ? <div className="table-card"><table><thead><tr><th>INVENTION</th><th>STATUS</th><th>VERSION</th><th>CREATED</th><th /></tr></thead><tbody>{inventions.map(item => <tr key={item.id}><td><Link className="invention-link" to={`/inventions/${item.id}`}>{item.title}</Link><small>{item.invention_number}</small></td><td><Status value={item.latest_status} /></td><td>{item.latest_version ? `v${item.latest_version}` : '—'}</td><td>{formatDate(item.created_at)}</td><td><Link className="row-arrow" to={`/inventions/${item.id}`}>→</Link></td></tr>)}</tbody></table></div> : <Empty title="No inventions yet" body={`There are no inventions for ${customers.find(c => String(c.id) === selected)?.name || 'this customer'}.`} action={<Link className="button secondary" to="/inventions/new">Create an invention</Link>} />}
    </>}
  </div>;
}

function Status({ value }) { const label = value ? value.charAt(0).toUpperCase() + value.slice(1) : 'Not started'; return <span className={`status ${value || 'pending'}`}><i />{label}</span>; }
function formatDate(value) { return value ? new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: 'numeric' }).format(new Date(value)) : '—'; }
function UploadField({ file, setFile, id = 'idf' }) { return <label className="upload-box" htmlFor={id}><input id={id} type="file" accept=".txt,text/plain" onChange={e => setFile(e.target.files?.[0] || null)} /><span className="upload-icon">↑</span><b>{file ? file.name : 'Choose a text file'}</b><small>{file ? `${(file.size / 1024).toFixed(0)} KB · UTF-8` : 'Upload IDF as .txt, UTF-8 encoded · Max 10 MB'}</small><span className="upload-browse">Browse files</span></label>; }

function NewInvention() {
  const navigate = useNavigate(); const [customers, setCustomers] = useState([]); const [customer, setCustomer] = useState(''); const [title, setTitle] = useState(''); const [file, setFile] = useState(null); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  useEffect(() => { api('/customers/').then(data => { setCustomers(data.customers); if (data.customers.length) setCustomer(String(data.customers[0].id)); }).catch(e => setError(message(e))); }, []);
  const submit = async e => { e.preventDefault(); setBusy(true); setError(''); const body = new FormData(); body.append('customer_id', customer); body.append('title', title); if (file) body.append('idf_file', file); try { const result = await api('/inventions/create/', { method: 'POST', body }); const notice = result.analysis_succeeded ? 'Invention created and analysis completed.' : 'Invention saved, but analysis failed. You can review the status and upload another version.'; navigate(`/inventions/${result.invention.id}`, { state: { notice } }); } catch (err) { setError(message(err)); } finally { setBusy(false); } };
  return <div className="content narrow"><PageTitle eyebrow="INVENTION INTAKE" title="New invention" description="Create a record and submit an invention disclosure for analysis." /><Notice error={error} />{!customers.length ? <div className="card"><Empty title="Add a customer first" body="Every invention belongs to a customer in your organization." action={<Link className="button primary" to="/customers/new">＋ Add customer</Link>} /></div> : <form className="card form" onSubmit={submit}><div className="section-heading"><span className="step">01</span><div><b>Invention details</b><small>Choose a customer and give this invention a short title.</small></div></div><label>Customer<select value={customer} onChange={e => setCustomer(e.target.value)} required>{customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label><label>Invention title<span className="field-hint">{title.length}/20</span><input value={title} maxLength={20} onChange={e => setTitle(e.target.value)} placeholder="e.g. Adaptive valve" required /></label><div className="section-heading section-spaced"><span className="step">02</span><div><b>Upload disclosure</b><small>Your IDF is stored with this version.</small></div></div><UploadField file={file} setFile={setFile} /><div className="form-actions"><Link className="button ghost" to="/inventions">Cancel</Link><button className="button primary" disabled={busy || !file}>{busy ? 'Generating analysis…' : 'Generate analysis'} <span>→</span></button></div></form>}</div>;
}

function NewCustomer() {
  const navigate = useNavigate(); 
  const [name, setName] = useState(''); 
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async e => 
    { e.preventDefault(); setBusy(true);
      setError(''); 
      try {
         await api('/customers/create/', { method: 'POST', body: JSON.stringify({ name }) });
         navigate('/inventions', { replace: true }); } 
      catch (err) { setError(message(err)); } 
      finally { setBusy(false); } };
  return <div className="content narrow">
        <PageTitle eyebrow="ORGANIZATION" title="Add a customer" description="Customers help you group invention disclosures within your workspace." />
        <Notice error={error} />
        <form className="card form" onSubmit={submit}>
          <label>Customer name<input value={name} maxLength={160} onChange={e => setName(e.target.value)} 
          placeholder="Enter customer or client name" required /></label>
          <div className="form-actions">
            <Link className="button ghost" to="/inventions">Cancel</Link>
            <button className="button primary" disabled={busy}>{busy ? 'Saving…' : 'Save customer'}</button></div></form></div>;
}

function InventionDetail() {
  const { id } = useParams(); const location = useLocation(); const [invention, setInvention] = useState(null); const [file, setFile] = useState(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const load = () => api(`/inventions/${id}/`).then(data => setInvention(data.invention)).catch(e => setError(message(e)));
  useEffect(() => { load(); }, [id]);
  const addVersion = async e => { e.preventDefault(); setBusy(true); setError(''); const form = new FormData(); if (file) form.append('idf_file', file); try { await api(`/inventions/${id}/versions/`, { method: 'POST', body: form }); setFile(null); e.target.reset(); await load(); } catch (err) { setError(message(err)); } finally { setBusy(false); } };
  const report = async version => { try { await downloadReport(version.id, `${invention.invention_number}-analysis-v${version.number}.docx`); } catch (e) { setError(message(e)); } };
  if (!invention) return <div className="content"><Notice error={error} /><div className="loading">Loading invention…</div></div>;
  return <div className="content"><div className="back-link"><Link to="/inventions">← My inventions</Link><span>/</span>{invention.customer.name}</div><PageTitle eyebrow={invention.invention_number} title={invention.title} description={`Customer · ${invention.customer.name}`} action={<Status value={invention.latest_status} />} /><Notice error={error} success={location.state?.notice} />
    <div className="split-heading"><div><h2>Analysis versions</h2><p>Each uploaded disclosure is saved as a separate version.</p></div></div>
    <div className="table-card version-table"><table><thead><tr><th>VERSION</th><th>SUBMITTED</th><th>STATUS</th><th>REPORT</th></tr></thead><tbody>{(invention.versions || []).map(version => <tr key={version.id}><td><b>Version {version.number}</b><small>{version.idf_filename}</small></td><td>{formatDate(version.completed_at || version.created_at)}</td><td><Status value={version.status} />{version.error_message && <small className="error-text">{version.error_message}</small>}</td><td>{version.has_report ? <button className="download-link" onClick={() => report(version)}>↓ Download report</button> : '—'}</td></tr>)}</tbody></table></div>
    <div className="card add-version"><div><div className="eyebrow">UPDATED DISCLOSURE</div><h2>Analyze a new version</h2><p>Upload a revised IDF to preserve the previous analysis and create a new version.</p></div><form className="version-form" onSubmit={addVersion}><UploadField file={file} setFile={setFile} id="new-version-idf" /><button className="button primary" disabled={busy || !file}>{busy ? 'Analyzing…' : 'Upload and analyze'} <span>→</span></button></form></div>
    {(invention.versions || []).filter(v => v.status === 'completed' && v.analysis_result).map(v => <Analysis key={v.id} version={v} />)}
  </div>;
}

function Analysis({ version }) {
  const result = version.analysis_result || {};
  const sections = Object.entries(result).filter(([, value]) => value !== null && value !== undefined && value !== '');
  return <details className="analysis-card"><summary><span className="analysis-heading"><b>Analysis results <span>Version {version.number}</span></b><small>Completed {formatDate(version.completed_at)}{sections.length ? ` · ${sections.length} sections` : ''}</small></span><span className="summary-toggle" aria-hidden="true">＋</span></summary><div className="analysis-content">{sections.length ? <div className="analysis-sections">{sections.map(([key, value], index) => <section className="analysis-section" key={key}><header><span className="analysis-section-number">{String(index + 1).padStart(2, '0')}</span><h3>{analysisLabel(key)}</h3></header><AnalysisValue value={value} fieldKey={key} /></section>)}</div> : <p className="muted">No structured analysis details were returned.</p>}</div></details>;
}

function analysisLabel(value) {
  return String(value).replace(/([a-z0-9])([A-Z])/g, '$1 $2').replaceAll('_', ' ').replace(/\b(cpc|npl|uspto|idf|api|url)\b/gi, word => word.toUpperCase()).replace(/\s+/g, ' ').trim();
}

const featureCollections = {
  structural_features: { heading: 'Structural features', title: 'Feature', description: 'feature' },
  procedural_features: { heading: 'Procedural features', title: 'Step', description: 'step' },
  functional_features: { heading: 'Functional features', title: 'Function', description: 'function' },
};

const keywordCollections = new Set(['structural_keywords', 'procedural_keywords', 'functional_keywords']);

function FeatureCollection({ rows, fieldKey }) {
  const config = featureCollections[fieldKey];
  return <div className="analysis-feature-list">{rows.map((item, index) => <article className="analysis-feature" key={item?.feature_id || index}>
    <div className="analysis-feature-primary"><div className="analysis-feature-id"><span>Feature ID</span><b>{item?.feature_id || '—'}</b></div><div className="analysis-feature-description"><h5>{config.title}</h5><AnalysisValue value={item?.[config.description]} /></div></div>
    <div className="analysis-feature-details"><h5>Technical details</h5><AnalysisValue value={item?.details} /></div>
  </article>)}</div>;
}

function InventionAnalysis({ value }) {
  return <div className="analysis-invention">
    {value.invention_summary && <section className="analysis-invention-summary"><h4>Invention summary</h4><AnalysisValue value={value.invention_summary} /></section>}
    {Object.entries(featureCollections).map(([key, config]) => Array.isArray(value[key]) && <section className="analysis-invention-group" key={key}><h4>{config.heading}</h4>{value[key].length ? <FeatureCollection rows={value[key]} fieldKey={key} /> : <span className="analysis-empty-value">No features provided</span>}</section>)}
  </div>;
}

function KeywordTerms({ value }) {
  const terms = Array.isArray(value) ? value : [value];
  return <div className="analysis-keyword-tags">{terms.map((term, index) => <span className="analysis-keyword-tag" key={`${term}-${index}`}>{String(term)}</span>)}</div>;
}

function KeywordTable({ rows }) {
  return <div className="analysis-keyword-table-wrap"><table className="analysis-keyword-table"><thead><tr><th>Feature ID</th><th>Feature</th><th>Primary keywords</th><th>Synonyms</th><th>Alternative terms</th></tr></thead><tbody>{rows.map((row, index) => <tr key={row?.feature_id || index}><td className="keyword-feature-id">{row?.feature_id || '—'}</td><td>{row?.feature || '—'}</td><td><KeywordTerms value={row?.primary_keywords || []} /></td><td><KeywordTerms value={row?.synonyms || []} /></td><td><KeywordTerms value={row?.alternative_terms || []} /></td></tr>)}</tbody></table></div>;
}

function KeywordAnalysisView({ value }) {
  const groups = Object.entries(value).filter(([key, rows]) => keywordCollections.has(key) && Array.isArray(rows));
  const consolidated = value.consolidated_keywords;
  return <div className="analysis-keyword-analysis">
    {groups.map(([key, rows]) => <section className="analysis-keyword-group" key={key}><h4>{analysisLabel(key)}</h4>{rows.length ? <KeywordTable rows={rows} /> : <span className="analysis-empty-value">No keywords available</span>}</section>)}
    {Array.isArray(consolidated) && <section className="analysis-keyword-group"><h4>Consolidated keywords</h4>{consolidated.length ? <KeywordTerms value={consolidated} /> : <span className="analysis-empty-value">No keywords available</span>}</section>}
  </div>;
}

function CpcCandidatesTable({ candidates }) {
  return <div className="analysis-cpc-table-wrap"><table className="analysis-cpc-table"><thead><tr><th>CPC code</th><th>Title</th><th>Relevance</th></tr></thead><tbody>{candidates.map((candidate, index) => <React.Fragment key={candidate?.cpc_code || index}><tr className="analysis-cpc-candidate"><td className="analysis-cpc-code">{candidate?.cpc_code || '—'}</td><td>{candidate?.title || '—'}</td><td>{candidate?.relevance || '—'}</td></tr><tr className="analysis-cpc-reason"><td colSpan={3}><span>Reason</span>{candidate?.reason || '—'}</td></tr></React.Fragment>)}</tbody></table></div>;
}

function CpcAnalysisView({ value }) {
  const candidates = Array.isArray(value.candidates) ? value.candidates : [];
  return <div className="analysis-cpc-analysis"><h4>Candidates</h4>{candidates.length ? <CpcCandidatesTable candidates={candidates} /> : <span className="analysis-empty-value">No CPC candidates available</span>}</div>;
}

function SearchQueriesTable({ queries }) {
  return <div className="analysis-query-table-wrap"><table className="analysis-query-table"><thead><tr><th>Query name</th><th>Search query</th><th>Priority</th></tr></thead><tbody>{queries.map((query, index) => <React.Fragment key={query?.query_name || index}><tr className="analysis-query-row"><td className="analysis-query-name">{query?.query_name || '—'}</td><td><code>{query?.query || '—'}</code></td><td><span className={`analysis-priority ${String(query?.priority || '').toLowerCase()}`}>{query?.priority || '—'}</span></td></tr><tr className="analysis-query-purpose"><td colSpan={3}><span>Purpose</span>{query?.purpose || '—'}</td></tr></React.Fragment>)}</tbody></table></div>;
}

function SearchQueryAnalysisView({ value }) {
  const queries = Array.isArray(value.queries) ? value.queries : [];
  return <div className="analysis-query-analysis"><h4>Search queries</h4>{queries.length ? <SearchQueriesTable queries={queries} /> : <span className="analysis-empty-value">No search queries available</span>}</div>;
}

function FeatureMappingTable({ ids, texts }) {
  const rowCount = Math.max(ids.length, texts.length);
  return <div className="analysis-feature-mapping-wrap"><table className="analysis-feature-mapping"><thead><tr><th>Feature ID</th><th>Feature text</th></tr></thead><tbody>{Array.from({ length: rowCount }, (_, index) => <tr key={`${ids[index] || 'feature'}-${index}`}><td className="analysis-cpc-code">{ids[index] || '—'}</td><td>{texts[index] || '—'}</td></tr>)}</tbody></table></div>;
}

function AnalysisValue({ value, fieldKey }) {
  if (value === null || value === undefined || value === '') return <span className="analysis-empty-value">—</span>;
  if (Array.isArray(value)) {
    if (!value.length) return <span className="analysis-empty-value">No items</span>;
    if (fieldKey === 'searched_feature_ids' || fieldKey === 'authors') return <KeywordTerms value={value} />;
    if (keywordCollections.has(fieldKey) && value.some(item => item && typeof item === 'object')) return <KeywordTable rows={value} />;
    if (fieldKey === 'consolidated_keywords' && value.every(item => typeof item === 'string')) return <KeywordTerms value={value} />;
    if (featureCollections[fieldKey]) {
      return <FeatureCollection rows={value} fieldKey={fieldKey} />;
    }
    return <ul className="analysis-list">{value.map((item, index) => <li className={item && typeof item === 'object' ? 'analysis-list-object' : ''} key={index}><AnalysisValue value={item} /></li>)}</ul>;
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value).filter(([, item]) => item !== null && item !== undefined && item !== '');
    if (!entries.length) return <span className="analysis-empty-value">No details</span>;
    if (Array.isArray(value.feature_ids) && Array.isArray(value.feature_texts)) {
      const remaining = entries.filter(([key]) => key !== 'feature_ids' && key !== 'feature_texts');
      return <div className="analysis-feature-mapping-block"><FeatureMappingTable ids={value.feature_ids} texts={value.feature_texts} />{remaining.length > 0 && <dl className="analysis-fields">{remaining.map(([key, item]) => <div className="analysis-field" key={key}><dt>{analysisLabel(key)}</dt><dd><AnalysisValue value={item} fieldKey={key} /></dd></div>)}</dl>}</div>;
    }
    if (Array.isArray(value.queries) && value.queries.some(query => query && typeof query === 'object' && 'query' in query)) return <SearchQueryAnalysisView value={value} />;
    if (Array.isArray(value.candidates) && value.candidates.some(candidate => candidate && typeof candidate === 'object' && 'cpc_code' in candidate)) return <CpcAnalysisView value={value} />;
    if (Object.entries(value).some(([key, item]) => keywordCollections.has(key) && Array.isArray(item)) || Array.isArray(value.consolidated_keywords)) return <KeywordAnalysisView value={value} />;
    if (Object.hasOwn(value, 'invention_summary') && Object.keys(featureCollections).some(key => Array.isArray(value[key]))) return <InventionAnalysis value={value} />;
    return <dl className="analysis-fields">{entries.map(([key, item]) => <div className="analysis-field" key={key}><dt>{analysisLabel(key)}</dt><dd><AnalysisValue value={item} fieldKey={key} /></dd></div>)}</dl>;
  }
  if (typeof value === 'boolean') return <span className={`analysis-bool ${value ? 'is-true' : 'is-false'}`}>{value ? 'Yes' : 'No'}</span>;
  return <p className="analysis-text">{String(value)}</p>;
}

function Help() { return <div className="content narrow"><PageTitle eyebrow="SUPPORT" title="Help" description="A quick guide to managing invention disclosures." /><div className="card help-card"><h2>Getting started</h2><ol><li>Select a customer or add one to your organization.</li><li>Create an invention with a title and UTF-8 text IDF file.</li><li>Open the invention to review analysis versions and download reports.</li><li>Upload a revised IDF from the invention page to create another version.</li></ol><h2>File format</h2><p>Version 1 accepts IDF documents as UTF-8 encoded <code>.txt</code> files, up to 10 MB.</p><h2>Need access?</h2><p>Accounts are provisioned by your organization administrator. Contact them if you need an account or your organization assignment changes.</p></div></div>; }

function RoutesRoot() { return <Routes><Route path="/login" element={<Login />} /><Route path="/forgot-password" element={<ForgotPassword />} /><Route path="/reset-password/:uid/:token" element={<ResetPassword />} /><Route element={<Protected />}><Route path="/inventions" element={<Inventions />} /><Route path="/inventions/new" element={<NewInvention />} /><Route path="/inventions/:id" element={<InventionDetail />} /><Route path="/customers/new" element={<NewCustomer />} /><Route path="/help" element={<Help />} /><Route path="*" element={<Navigate to="/inventions" replace />} /></Route></Routes>; }

createRoot(document.getElementById('root')).render(<React.StrictMode><BrowserRouter><AuthProvider><RoutesRoot /></AuthProvider></BrowserRouter></React.StrictMode>);
