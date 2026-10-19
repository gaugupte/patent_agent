import React, { createContext, useContext, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Link, Navigate, Outlet, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom';
import { api, downloadReport } from './api';
import './styles.css';

const Auth = createContext(null);
const useAuth = () => useContext(Auth);
const message = (error) => error instanceof Error ? error.message : 'Something went wrong.';

function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined);
  const refresh = () => api('/auth/me/').then(setUser).catch(() => setUser(null));
  useEffect(() => { refresh(); }, []);
  return <Auth.Provider value={{ user, setUser, refresh }}>{children}</Auth.Provider>;
}

function Protected() {
  const { user } = useAuth();
  const location = useLocation();
  if (user === undefined) return <div className="loading">Loading your workspace…</div>;
  return user ? <Shell><Outlet /></Shell> : <Navigate to="/login" replace state={{ from: location.pathname }} />;
}

function Shell({ children }) {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
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
  const navigate = useNavigate(); const [name, setName] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const submit = async e => { e.preventDefault(); setBusy(true); setError(''); try { await api('/customers/create/', { method: 'POST', body: JSON.stringify({ name }) }); navigate('/inventions', { replace: true }); } catch (err) { setError(message(err)); } finally { setBusy(false); } };
  return <div className="content narrow"><PageTitle eyebrow="ORGANIZATION" title="Add a customer" description="Customers help you group invention disclosures within your workspace." /><Notice error={error} /><form className="card form" onSubmit={submit}><label>Customer name<input value={name} maxLength={160} onChange={e => setName(e.target.value)} placeholder="Enter customer or client name" required /></label><div className="form-actions"><Link className="button ghost" to="/inventions">Cancel</Link><button className="button primary" disabled={busy}>{busy ? 'Saving…' : 'Save customer'}</button></div></form></div>;
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
  return <details className="analysis-card"><summary><span><b>Analysis results · Version {version.number}</b><small>Completed {formatDate(version.completed_at)}</small></span><span className="summary-toggle">＋</span></summary><div className="analysis-content">{sections.length ? sections.map(([key, value]) => <section key={key}><h3>{key.replaceAll('_', ' ')}</h3><AnalysisValue value={value} /></section>) : <p className="muted">No structured analysis details were returned.</p>}</div></details>;
}
function AnalysisValue({ value }) { if (Array.isArray(value)) return <ul>{value.map((item, i) => <li key={i}>{typeof item === 'object' ? <AnalysisValue value={item} /> : String(item)}</li>)}</ul>; if (value && typeof value === 'object') return <dl>{Object.entries(value).map(([k, v]) => <React.Fragment key={k}><dt>{k.replaceAll('_', ' ')}</dt><dd><AnalysisValue value={v} /></dd></React.Fragment>)}</dl>; return <p>{String(value)}</p>; }

function Help() { return <div className="content narrow"><PageTitle eyebrow="SUPPORT" title="Help" description="A quick guide to managing invention disclosures." /><div className="card help-card"><h2>Getting started</h2><ol><li>Select a customer or add one to your organization.</li><li>Create an invention with a title and UTF-8 text IDF file.</li><li>Open the invention to review analysis versions and download reports.</li><li>Upload a revised IDF from the invention page to create another version.</li></ol><h2>File format</h2><p>Version 1 accepts IDF documents as UTF-8 encoded <code>.txt</code> files, up to 10 MB.</p><h2>Need access?</h2><p>Accounts are provisioned by your organization administrator. Contact them if you need an account or your organization assignment changes.</p></div></div>; }

function RoutesRoot() { return <Routes><Route path="/login" element={<Login />} /><Route path="/forgot-password" element={<ForgotPassword />} /><Route path="/reset-password/:uid/:token" element={<ResetPassword />} /><Route element={<Protected />}><Route path="/inventions" element={<Inventions />} /><Route path="/inventions/new" element={<NewInvention />} /><Route path="/inventions/:id" element={<InventionDetail />} /><Route path="/customers/new" element={<NewCustomer />} /><Route path="/help" element={<Help />} /><Route path="*" element={<Navigate to="/inventions" replace />} /></Route></Routes>; }

createRoot(document.getElementById('root')).render(<React.StrictMode><BrowserRouter><AuthProvider><RoutesRoot /></AuthProvider></BrowserRouter></React.StrictMode>);
