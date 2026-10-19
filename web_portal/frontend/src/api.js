const csrf = async () => {
  const response = await fetch('/api/csrf/', { credentials: 'include' });
  if (!response.ok) throw new Error('Could not start a secure session. Refresh and try again.');
  return (await response.json()).csrfToken;
};

export async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  if (!['GET', 'HEAD', 'OPTIONS'].includes((options.method || 'GET').toUpperCase())) {
    headers.set('X-CSRFToken', await csrf());
  }
  const response = await fetch(`/api${path}`, { ...options, headers, credentials: 'include' });
  const type = response.headers.get('content-type') || '';
  const payload = type.includes('application/json') ? await response.json() : null;
  if (!response.ok) throw new Error(payload?.detail || 'The request could not be completed.');
  return payload;
}

export async function downloadReport(versionId, suggestedName) {
  const response = await fetch(`/api/versions/${versionId}/report/`, { credentials: 'include' });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || 'The report could not be downloaded.');
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = suggestedName;
  link.click();
  URL.revokeObjectURL(url);
}
