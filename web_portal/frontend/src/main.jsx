import React, { createContext, useContext, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Link, Navigate, Outlet, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom';
import { api, downloadReport } from './api';
import './styles.css';
import './auth.css';
import './billing.css';

const Auth = createContext(null);
const useAuth = () => useContext(Auth); // #this is function definition
const message = (error) => error instanceof Error ? error.message : 'Something went wrong.';

// this a component that provides authentication context to its children. It manages the user state and provides a refresh function to fetch the current user data from the API.
function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined);   // hook to manage user state, initially undefined. setUser is a function to update the user state.
  const refresh = () => api('/auth/me/').then(setUser).catch(() => setUser(null));
  useEffect(() => { refresh(); const onAccessExpired = () => refresh(); window.addEventListener('portal-access-expired', onAccessExpired); return () => window.removeEventListener('portal-access-expired', onAccessExpired); }, []); // Refresh account access state after a backend subscription or trial expiry response.
  useEffect(() => { if (!user?.trial_active || !user.trial_ends_at) return undefined; const timer = window.setTimeout(refresh, Math.max(0, new Date(user.trial_ends_at).getTime() - Date.now())); return () => window.clearTimeout(timer); }, [user?.trial_active, user?.trial_ends_at]);
  return <Auth.Provider value={{ user, setUser, refresh }}>{children}</Auth.Provider>;
}

// Protected component checks if the user is authenticated. If the user is undefined, it shows a loading message. If the user is authenticated, it renders the Shell component with the Outlet for nested routes. If the user is not authenticated, it redirects to the login page.
// it is called in the RoutesRoot component to protect certain routes that require authentication.
function Protected() {
  const { user } = useAuth();
  const location = useLocation();
  if (user === undefined) return <div className="loading">Loading your workspace…</div>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (!user.access_active) {
    const canManage = user.role === 'organization_admin';
    if (canManage && location.pathname === '/organization') return <Shell><Outlet /></Shell>;
    return canManage ? <Navigate to="/organization" replace /> : <Shell><SubscriptionRequired /></Shell>;
  }
  return <Shell><Outlet /></Shell>;
}

function Shell({ children }) {
  const { user, setUser } = useAuth();// useAuth hook to access the user state and setUser function from the Auth context.
  const navigate = useNavigate(); // useNavigate hook to programmatically navigate to different routes.
  const location = useLocation(); // useLocation hook to access the current location object, which contains information about the current URL.
  const signOut = async () => { try { await api('/auth/logout/', { method: 'POST' }); } finally { setUser(null); navigate('/login'); } };
  return <div className="app-shell">
    <aside className="sidebar">
      <Link to="/inventions" className="brand"><BrandMark /><span>PatentDesk</span></Link>
      <div className="workspace-label">WORKSPACE</div>
      <div className="org-chip"><span className="org-dot" />{user?.organization?.name}</div>
      <nav className="nav-links">
        {user?.role === 'organization_admin' && <Link className={location.pathname === '/organization' ? 'active' : ''} to="/organization"><span>⚙</span>{user?.organization?.access_type === 'individual' ? 'My subscription' : 'Organization'}</Link>}
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

function BrandMark({ large = false }) { return <span className={`brand-mark${large ? ' brand-mark-large' : ''}`} aria-label="PatentDesk"><span>P</span><span>D</span></span>; }

function Welcome() {
  const { user } = useAuth();
  if (user === undefined) return <div className="loading">Loading PatentDesk…</div>;
  if (user) return <Navigate to={user.access_active ? '/inventions' : '/organization'} replace />;
  return <AuthFrame><div className="auth-card welcome-card"><BrandMark large /><div className="eyebrow">INVENTION ANALYSIS WORKSPACE</div><h1>Welcome to PatentDesk</h1><p className="muted">Sign in to your workspace or create an account to get started.</p><div className="welcome-actions"><Link className="button primary full" to="/login">Sign in</Link><Link className="button secondary full" to="/register">Register</Link></div></div><div className="auth-foot">PatentDesk</div></AuthFrame>;
}

function Login() {
  const { user, setUser } = useAuth(); const navigate = useNavigate(); const location = useLocation();
  const [username, setUsername] = useState(''); const [password, setPassword] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/inventions" replace />;
  const submit = async (event) => { event.preventDefault(); setBusy(true); setError(''); try { setUser(await api('/auth/login/', { method: 'POST', body: JSON.stringify({ username, password }) })); navigate(location.state?.from || '/inventions', { replace: true }); } catch (e) { setError(message(e)); } finally { setBusy(false); } };
  const authError = new URLSearchParams(location.search).get('auth_error');
  const providerError = authError === 'google_not_configured' ? 'Google sign-in has not been configured yet.' : authError === 'account_conflict' ? 'More than one portal account uses this email. Contact your administrator.' : authError === 'account_inactive' ? 'This portal account is inactive or not assigned to an active organization. Contact your administrator.' : authError === 'session_already_active' ? 'This account is already signed in on another browser or device. Sign out there before trying again.' : authError === 'registration_required' ? 'Choose an access type and complete registration before signing in.' : authError === 'password_login_required' ? 'This paid individual account must use its username and password.' : authError ? 'Google sign-in could not be completed. Please try again.' : '';
  return <AuthFrame><div className="auth-card"><BrandMark large /><div className="eyebrow">ACCOUNT SIGN IN</div><h1>Sign in to PatentDesk</h1><p className="muted">Use your username and password. This sign-in works for individual and organization accounts.</p><Notice error={error || providerError} />
    <form onSubmit={submit} className="form"><label>Username<input autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required /></label><label>Password<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></label><button className="button primary full" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button></form>
    <Link className="auth-link" to="/forgot-password">Forgot password?</Link>
    <Link className="auth-link" to="/register?access=individual">Trial account? Choose individual access</Link>
    <Link className="auth-link" to="/">Back to welcome</Link>
    <Link className="auth-link" to="/register">Register</Link>
  </div><div className="auth-foot">PatentDesk</div></AuthFrame>;
}

function Register() {
  const navigate = useNavigate(); const { setUser } = useAuth();
  const [accessType, setAccessType] = useState(() => new URLSearchParams(window.location.search).get('access') === 'individual' ? 'individual' : '');
  const [individualPath, setIndividualPath] = useState('');
  const [plans, setPlans] = useState([]); const [planId, setPlanId] = useState('');
  const [email, setEmail] = useState(''); const [individualName, setIndividualName] = useState(''); const [organizationName, setOrganizationName] = useState(''); const [seatCount, setSeatCount] = useState(1);
  const [username, setUsername] = useState(''); const [password, setPassword] = useState(''); const [passwordConfirmation, setPasswordConfirmation] = useState('');
  const [intent, setIntent] = useState(''); const [codeSent, setCodeSent] = useState(false); const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [success, setSuccess] = useState('');
  useEffect(() => { api('/auth/plans/').then(data => { setPlans(data.plans); if (data.plans.length) setPlanId(String(data.plans[0].id)); }).catch(e => setError(message(e))); }, []);
  const begin = async event => {
    event?.preventDefault(); if (event?.currentTarget?.form && !event.currentTarget.form.reportValidity()) return; setBusy(true); setError(''); setSuccess('');
    try {
      const isTrial = accessType === 'individual' && individualPath === 'trial';
      const needsPasswordLogin = (accessType === 'individual' && !isTrial) || accessType === 'organization';
      const result = await api('/auth/register/start/', { method: 'POST', body: JSON.stringify({ access_type: accessType, start_trial: isTrial, email, individual_name: individualName, organization_name: organizationName, plan_id: isTrial ? null : planId, seat_count: accessType === 'individual' ? 1 : Number(seatCount), username: needsPasswordLogin ? username : undefined, password: needsPasswordLogin ? password : undefined, password_confirmation: needsPasswordLogin ? passwordConfirmation : undefined }) });
      setIntent(result.registration_intent);
      await api('/auth/email-code/request/', { method: 'POST', body: JSON.stringify({ email }) });
      setCodeSent(true); setSuccess(isTrial ? `Seven-day trial ready. No payment is required. A verification code was sent to ${email}.` : accessType === 'organization' ? `A verification code was sent to ${email}.` : `${result.detail} A verification code was sent to ${email}.`);
    } catch (e) { setError(message(e)); } finally { setBusy(false); }
  };
  const verify = async event => {
    event.preventDefault(); setBusy(true); setError('');
    try { const user = await api('/auth/email-code/verify/', { method: 'POST', body: JSON.stringify({ email, code, registration_intent: intent }) }); setUser(user); navigate('/inventions', { replace: true }); }
    catch (e) { setError(message(e)); } finally { setBusy(false); }
  };
  const authError = new URLSearchParams(window.location.search).get('auth_error');
  const registrationMessage = authError === 'registration_required' ? 'Choose an access type and plan to create your account.' : authError === 'registration_expired' ? 'Your registration checkout expired. Please start again.' : authError === 'registration_email_mismatch' ? 'The verified email does not match the address entered during registration.' : authError === 'registration_conflict' ? 'An account or organization with those details already exists. Sign in or use another organization name.' : authError === 'individual_email_required' ? 'Direct individual registration uses email verification plus the username and password you choose.' : authError === 'google_signup_disabled' ? 'Google signup is unavailable. Create your account with email verification, username, and password.' : '';
  const individualTrial = accessType === 'individual' && individualPath === 'trial';
  const individualPaid = accessType === 'individual' && individualPath === 'paid';
  return <AuthFrame><div className="auth-card"><BrandMark large /><div className="eyebrow">{accessType === 'organization' ? 'ORGANIZATION SIGNUP' : accessType === 'individual' ? 'INDIVIDUAL SIGNUP' : 'CREATE ACCOUNT'}</div><h1>Choose your access{accessType && ` (${accessType === 'individual' ? 'Individual' : 'Organization'})`}</h1><p className="muted">Individuals can start one seven-day trial with email verification or register directly with a plan, username, and password. Organization admins choose seats, a plan, username, and password. The first user of an organization automatically becomes its admin.</p><Notice error={error || registrationMessage} success={codeSent ? '' : success} />
    {!accessType ? <div className="access-options"><button className="access-option" onClick={() => setAccessType('individual')}><b>Individual</b><span>Try the product for seven days or buy one seat now.</span></button><button className="access-option" onClick={() => setAccessType('organization')}><b>Organization</b><span>Choose seats for your team and manage members.</span></button></div> : <>
      <button className="auth-link-button" onClick={() => { setAccessType(''); setIndividualPath(''); setIntent(''); setCodeSent(false); setCode(''); setPassword(''); setPasswordConfirmation(''); setError(''); setSuccess(''); }}>← Change access type</button>
      {accessType === 'individual' && !individualPath && <div className="access-options"><button className="access-option" onClick={() => { setIndividualPath('trial'); setError(''); setSuccess(''); }}><b>Start free trial</b><span>One seven-day trial, verified with Gmail or an email code.</span></button><button className="access-option" onClick={() => { setIndividualPath('paid'); setError(''); setSuccess(''); }}><b>Register with a plan</b><span>Buy one seat now and create your username and password.</span></button></div>}
      {accessType === 'individual' && individualPath && <button className="auth-link-button" onClick={() => { setIndividualPath(''); setIntent(''); setCodeSent(false); setCode(''); setPassword(''); setPasswordConfirmation(''); setError(''); setSuccess(''); }}>← Choose trial or paid registration</button>}
      {codeSent ? <form className="form" onSubmit={verify}><p className="muted">{success} Enter the 6-digit code sent to <b>{email}</b>.{individualTrial ? ' This starts your one-time seven-day trial.' : individualPaid ? ` Your password was checked during registration. Confirm your email to finish account creation for one seat. Username: ${username}.` : ` Confirmation will create the organization admin account. Username: ${username}.`}</p><label>Verification code<input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={code} onChange={e => setCode(e.target.value)} required /></label><button className="button primary full" disabled={busy}>{busy ? 'Verifying…' : individualPaid ? 'Confirm email and register' : individualTrial ? 'Start free trial' : 'Verify and create account'}</button></form> : (individualPath || accessType === 'organization') && <form className="form" onSubmit={event => event.preventDefault()}>
        <label>Email address<input type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} required /></label>
        {accessType === 'individual' && <label>Your name<input autoComplete="name" maxLength={160} value={individualName} onChange={e => setIndividualName(e.target.value)} required /></label>}
        {(individualPaid || accessType === 'organization') && <><label>Choose username<input autoComplete="username" maxLength={16} value={username} onChange={e => setUsername(e.target.value)} required /></label><label>Create password<input type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} required /><small className="password-criteria">Use at least 8 characters. Avoid common passwords, all-numeric passwords, and passwords too similar to your username, name, or email.</small></label><label>Confirm password<input type="password" autoComplete="new-password" value={passwordConfirmation} onChange={e => setPasswordConfirmation(e.target.value)} required /></label></>}
        {accessType === 'organization' && <label>Organization name<input maxLength={160} value={organizationName} onChange={e => setOrganizationName(e.target.value)} required /></label>}
        {(individualPaid || accessType === 'organization') && <><label>Plan<select value={planId} onChange={e => setPlanId(e.target.value)} required>{plans.map(plan => <option key={plan.id} value={plan.id}>{plan.name} · {plan.billing_interval_label} · ₹{plan.discounted_price}/seat{Number(plan.discount_percent) > 0 ? ` (${plan.discount_percent}% discount)` : ''}</option>)}</select></label>{individualPaid ? <div className="simulated-payment">One seat for your individual workspace. Test checkout only; no real payment will be taken.</div> : <><label>Seats to purchase<input type="number" min="1" max="500" value={seatCount} onChange={e => setSeatCount(e.target.value)} required /><small className="field-hint">Includes your organization administrator seat.</small></label><div className="simulated-payment">Test checkout only · no real payment will be taken.</div></>}</>}
        {individualTrial && <div className="simulated-payment">Start your one-time seven-day trial with an email verification code. No payment is required.</div>}
        {individualTrial ? <button type="button" className="button primary full" disabled={busy} onClick={event => begin(event)}>{busy ? 'Sending verification code…' : 'Start trial with email code'}</button> : <button type="button" className="button primary full" disabled={busy || !plans.length || !planId} onClick={event => begin(event)}>{busy ? (individualPaid ? 'Preparing registration…' : 'Preparing test checkout…') : 'Continue with email verification'}</button>}
      </form>}
    </>}
    <Link className="auth-link" to="/login">Already have an account? Sign in</Link>
  </div><div className="auth-foot">PatentDesk · Test subscription checkout</div></AuthFrame>;
}

function SubscriptionRequired() { return <div className="content narrow"><PageTitle eyebrow="SUBSCRIPTION" title="Access expired" description="Your assigned subscription is not currently active." /><div className="card"><p>Access to inventions and analysis stops immediately when the subscription expires. Please contact your organization administrator to assign or renew a seat.</p><button className="button ghost" onClick={async () => { await api('/auth/logout/', { method: 'POST' }).catch(() => {}); window.location.assign('/login'); }}>Sign out</button></div></div>; }

function AuthFrame({ children }) { return <div className="auth-page"><Link to="/" className="auth-brand" aria-label="PatentDesk home"><BrandMark /> <span>PatentDesk</span></Link>{children}</div>; }

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

function FeatureMappingTable({ features = [], ids = [], texts = [] }) {
  const rows = features.length ? features : Array.from({ length: Math.max(ids.length, texts.length) }, (_, index) => ({ feature_id: ids[index], text: texts[index] }));
  return <div className="analysis-feature-mapping-wrap"><table className="analysis-feature-mapping"><thead><tr><th>Feature ID</th><th>Feature text</th></tr></thead><tbody>{rows.map((feature, index) => <tr key={`${feature?.feature_id || 'feature'}-${index}`}><td className="analysis-cpc-code">{feature?.feature_id || '—'}</td><td>{feature?.text || '—'}</td></tr>)}</tbody></table></div>;
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
    if ((Array.isArray(value.features) && value.features.some(feature => feature && typeof feature === 'object' && 'text' in feature)) || (Array.isArray(value.feature_ids) && Array.isArray(value.feature_texts))) {
      const remaining = entries.filter(([key]) => !['features', 'feature_ids', 'feature_texts'].includes(key));
      return <div className="analysis-feature-mapping-block"><FeatureMappingTable features={value.features || []} ids={value.feature_ids || []} texts={value.feature_texts || []} />{remaining.length > 0 && <dl className="analysis-fields">{remaining.map(([key, item]) => <div className="analysis-field" key={key}><dt>{analysisLabel(key)}</dt><dd><AnalysisValue value={item} fieldKey={key} /></dd></div>)}</dl>}</div>;
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

function OrganizationPage() {
  const { user, refresh } = useAuth();
  const [billing, setBilling] = useState(null); const [plans, setPlans] = useState([]);
  const [planId, setPlanId] = useState(''); const [seatCount, setSeatCount] = useState(1); const [email, setEmail] = useState(''); const [purchaseId, setPurchaseId] = useState('');
  const [password, setPassword] = useState(''); const [passwordConfirmation, setPasswordConfirmation] = useState('');
  const [error, setError] = useState(''); const [success, setSuccess] = useState(''); const [busy, setBusy] = useState(false);
  const load = () => api('/auth/organization/billing/').then(data => { setBilling(data); setPurchaseId(current => data.purchases.find(item => item.available > 0 && String(item.id) === current)?.id || data.purchases.find(item => item.available > 0)?.id?.toString() || ''); }).catch(e => setError(message(e)));
  useEffect(() => { load(); api('/auth/plans/').then(data => { setPlans(data.plans); if (data.plans.length) setPlanId(String(data.plans[0].id)); }).catch(e => setError(message(e))); }, []);
  const purchase = async event => { event.preventDefault(); setBusy(true); setError(''); setSuccess(''); try { const result = await api('/auth/organization/purchase-seats/', { method: 'POST', body: JSON.stringify({ plan_id: planId, seat_count: Number(seatCount), password, password_confirmation: passwordConfirmation }) }); setSuccess(result.detail); setPassword(''); setPasswordConfirmation(''); await load(); await refresh(); } catch (e) { setError(message(e)); } finally { setBusy(false); } };
  const addUser = async event => { event.preventDefault(); setBusy(true); setError(''); setSuccess(''); try { await api('/auth/organization/users/', { method: 'POST', body: JSON.stringify({ email, purchase_id: purchaseId }) }); setEmail(''); setSuccess('User added and assigned the selected plan seat. They can sign in with Google or an email verification code.'); await load(); } catch (e) { setError(message(e)); } finally { setBusy(false); } };
  const removeUser = async user => { setBusy(true); setError(''); setSuccess(''); try { await api(`/auth/organization/users/${user.id}/remove/`, { method: 'POST' }); setSuccess(`${user.email} was disabled and the seat released.`); await load(); } catch (e) { setError(message(e)); } finally { setBusy(false); } };
  const individual = billing?.organization?.access_type === 'individual';
  const portalAdmin = Boolean(user?.is_portal_admin);
  const trialEnds = billing?.trial_ends_at ? new Date(billing.trial_ends_at).toLocaleString() : '';
  const subscriptionEnds = billing?.subscription_ends_at ? new Date(billing.subscription_ends_at).toLocaleDateString() : '';
  const paidAccessActive = Boolean(billing?.subscription_active);
  const pageTitle = portalAdmin && individual ? 'Portal administrator' : individual ? (billing?.trial_active ? 'Your seven-day trial' : paidAccessActive ? 'Your subscription' : user?.password_login_enabled ? 'Renew subscription' : 'Complete registration') : 'Organization access';
  const pageDescription = portalAdmin && individual ? 'Portal administrator access does not expire with a trial or subscription.' : individual ? (billing?.trial_active ? 'Your individual trial is active.' : paidAccessActive ? `Your individual plan is active through ${subscriptionEnds}.` : user?.password_login_enabled ? 'Your subscription has expired. Choose a plan to restore access.' : 'Your trial has ended. Choose a plan and set a password to continue.') : 'Purchase seats with a simulated checkout, then assign each seat to a user.';
  return <div className="content"><PageTitle eyebrow={individual ? 'INDIVIDUAL PLAN' : 'ORGANIZATION ADMIN'} title={pageTitle} description={pageDescription} />
    <Notice error={error} success={success} />
    {portalAdmin && individual && <div className="trial-banner"><b>Portal administrator access is exempt</b><span>This account will not lose portal access when a trial or subscription expires.</span></div>}
    {individual && !portalAdmin && paidAccessActive && <div className="trial-banner"><b>Your paid access is active</b><span>Your plan is valid through {subscriptionEnds}. Sign in with username <strong>{user?.username}</strong> and your password.</span></div>}
    {individual && !portalAdmin && !billing?.trial_active && !user?.password_login_enabled && <div className="trial-ended-notice"><b>Your seven-day free trial has ended. Buy access to continue.</b><p>It ended {trialEnds}. Your invention workspace is paused until you complete registration:</p><ol><li>Select a plan below and complete the simulated checkout. No real payment is collected in this test version.</li><li>Create and confirm a password for your account.</li><li>Your username is <strong>{user?.username}</strong>. After checkout, sign in with this username and the password you created. Google and email-code sign-in are only for the trial.</li></ol></div>}
    {portalAdmin && individual ? null : !individual || !billing?.trial_active ? <div className="billing-summary"><div className="card"><small>Purchased seats</small><b>{billing?.seat_count ?? '—'}</b></div><div className="card"><small>Assigned seats</small><b>{billing?.assigned_seats ?? '—'}</b></div><div className="card"><small>Available seats</small><b>{billing?.available_seats ?? '—'}</b></div></div> : <div className="trial-banner"><b>Trial access is active</b><span>Your trial ends {trialEnds}. You can keep using the portal until then.</span></div>}
    {(portalAdmin && individual) || (individual && (billing?.trial_active || paidAccessActive)) ? null : <div className="organization-grid"><section className="card"><h2>{individual ? 'Choose a plan and register' : 'Purchase seats'}</h2><p className="muted">Choose the plan{individual ? '' : ' and number of seats'} first. Test checkout creates active access without charging money.</p><form className="form" onSubmit={purchase}><label>Plan<select value={planId} onChange={e => setPlanId(e.target.value)} required>{plans.map(plan => <option key={plan.id} value={plan.id}>{plan.name} · {plan.billing_interval_label} · ₹{plan.discounted_price}/seat</option>)}</select></label>{!individual && <label>Number of seats<input type="number" min="1" max="500" value={seatCount} onChange={e => setSeatCount(e.target.value)} required /></label>}{individual && <><div className="login-identity">Your login username is <b>{user?.username}</b>.</div>{!user?.password_login_enabled && <><label>Create password<input type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} required /></label><label>Confirm password<input type="password" autoComplete="new-password" value={passwordConfirmation} onChange={e => setPasswordConfirmation(e.target.value)} required /></label></>}</>}<div className="simulated-payment">Simulation only · no payment is collected.{!individual && ' One seat is assigned to the organization administrator.'}</div><button className="button primary" disabled={busy || !planId}>{busy ? 'Processing…' : individual ? 'Complete registration and subscribe' : 'Simulate purchase'}</button></form></section>
    {!individual && <section className="card"><h2>Add a user</h2><p className="muted">Choose which purchased plan seat to assign. A user can be added only when that purchase has an available seat.</p><form className="form" onSubmit={addUser}><label>User email<input type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} required /></label><label>Purchased plan<select value={purchaseId} onChange={e => setPurchaseId(e.target.value)} required><option value="">Choose an available seat</option>{(billing?.purchases || []).filter(item => item.available > 0).map(item => <option key={item.id} value={item.id}>{item.plan.name} · {item.plan.billing_interval_label} · valid through {item.ends_at} · {item.available} available</option>)}</select></label><button className="button primary" disabled={busy || !purchaseId}>{busy ? 'Adding…' : 'Add organization user'}</button>{billing?.available_seats === 0 && <small className="field-hint">Purchase more seats before adding another user.</small>}</form></section>}</div>}
    {!individual && <><div className="split-heading"><h2>Users</h2><p>Access ends immediately on the subscription end date.</p></div>
    <div className="table-card"><table><thead><tr><th>USER</th><th>ROLE</th><th>PLAN</th><th>VALID THROUGH</th><th>STATUS</th><th></th></tr></thead><tbody>{(billing?.users || []).map(user => <tr key={user.id}><td><b>{user.email}</b><small>{user.username}</small></td><td>{user.role === 'organization_admin' ? 'Organization admin' : 'Member'}</td><td>{user.plan ? `${user.plan.name} · ${user.plan.billing_interval_label}` : 'No active seat'}</td><td>{user.ends_at || '—'}</td><td>{user.is_active && user.ends_at ? 'Active' : 'Inactive'}</td><td>{user.role !== 'organization_admin' && user.is_active && <button className="table-action" disabled={busy} onClick={() => removeUser(user)}>Remove</button>}</td></tr>)}</tbody></table>{!billing?.users?.length && <p className="table-empty">No users yet.</p>}</div></>}
    {(!portalAdmin || !individual) && <><div className="split-heading"><h2>Seat purchases</h2><p>Purchases are marked as simulated and no card or payment details are collected.</p></div>
    <div className="table-card"><table><thead><tr><th>PLAN</th><th>SEATS</th><th>ASSIGNED</th><th>VALIDITY</th><th>TOTAL</th><th>MODE</th></tr></thead><tbody>{(billing?.purchases || []).map(item => <tr key={item.id}><td>{item.plan.name} · {item.plan.billing_interval_label}</td><td>{item.seat_count}</td><td>{item.assigned}</td><td>{item.starts_at} — {item.ends_at}</td><td>₹{item.total_price}</td><td>{item.payment_mode}</td></tr>)}</tbody></table>{!billing?.purchases?.length && <p className="table-empty">No purchases yet.</p>}</div>
    </>}
  </div>;
}

function Help() { return <div className="content narrow"><PageTitle eyebrow="SUPPORT" title="Help" description="A quick guide to managing invention disclosures." /><div className="card help-card"><h2>Getting started</h2><ol><li>Select a customer or add one to your workspace.</li><li>Create an invention with a title and UTF-8 text IDF file.</li><li>Open the invention to review analysis versions and download reports.</li><li>Upload a revised IDF from the invention page to create another version.</li></ol><h2>File format</h2><p>Version 1 accepts IDF documents as UTF-8 encoded <code>.txt</code> files, up to 10 MB.</p><h2>Need access?</h2><p>Individuals can sign up with Google or an email verification code. Organization users should use an account linked to their organization; contact its administrator if you need access or your organization assignment changes.</p></div></div>; }

function RoutesRoot() { return <Routes><Route path="/" element={<Welcome />} /><Route path="/login" element={<Login />} /><Route path="/register" element={<Register />} /><Route path="/forgot-password" element={<ForgotPassword />} /><Route path="/reset-password/:uid/:token" element={<ResetPassword />} /><Route element={<Protected />}><Route path="/organization" element={<OrganizationPage />} /><Route path="/inventions" element={<Inventions />} /><Route path="/inventions/new" element={<NewInvention />} /><Route path="/inventions/:id" element={<InventionDetail />} /><Route path="/customers/new" element={<NewCustomer />} /><Route path="/help" element={<Help />} /><Route path="*" element={<Navigate to="/inventions" replace />} /></Route></Routes>; }

createRoot(document.getElementById('root')).render(<React.StrictMode><BrowserRouter><AuthProvider><RoutesRoot /></AuthProvider></BrowserRouter></React.StrictMode>);
