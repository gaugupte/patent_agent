const csrf = async () => {
  const response = await fetch('/api/csrf/', { credentials: 'include' });
  if (!response.ok) throw new Error('Could not start a secure session. Refresh and try again.');
  return (await response.json()).csrfToken;
};

// This function is used to make API requests to the backend. It takes a path and an options object as parameters. 
// It sets the appropriate headers, including the CSRF token for non-GET requests, and makes a fetch request to the specified API endpoint.
//A fetch request is a browser’s built-in way to send an HTTP request to a server and receive its response.
// Here, fetch('/api/customers/create/', ...) sends the customer data from React to Django and waits for Django’s reply.
// If the response is not ok, it throws an error with a message from the response payload or a default message. 
// If the response is ok, it returns the parsed JSON payload.
// - `export` lets other files import this function, such as `main.jsx`.
//- `async` lets it wait for the CSRF request and the main request.
//- `path` is the API endpoint suffix.
//- `options = {}` means callers can omit options; the function then uses an empty object.

export async function api(path, options = {}) {
  const headers = new Headers(options.headers || {}); // Creates a browser `Headers` object. It starts with any headers the caller supplied; if none were supplied, it starts empty.
  
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json'); 
  // If there is a request body and it is **not** a `FormData` upload, tell Django to expect JSON.
  // For the new-customer example, the body is JSON, so this sets the header. 
  // For an invention file upload, the body is `FormData`; the browser sets the correct multipart header itself, including its boundary.
  
  if (!['GET', 'HEAD', 'OPTIONS'].includes((options.method || 'GET').toUpperCase())) {
    headers.set('X-CSRFToken', await csrf());
  }
  //For methods that can change data—such as `POST`, `PUT`, `PATCH`, or `DELETE`—this gets a CSRF token and adds it to the request headers.
  //If no method is specified, it defaults to `GET`, which does not need this token. In the customer example, the method is `POST`, so the helper calls `csrf()` first. That function gets a token from Django at `/api/csrf/`.
  
  const response = await fetch(`/api${path}`, { ...options, headers, credentials: 'include' });
  // Sends the request and waits for the server’s response.
  // For the customer example, the URL becomes:
  //```text
  // /api/customers/create/
  //```
  // `...options` passes the caller’s method and body into `fetch`. 
  // The helper supplies the prepared headers and `credentials: 'include'`, // which tells the browser to include cookies such as Django’s login session cookie.

  const type = response.headers.get('content-type') || ''; // Reads the server’s `Content-Type` header. If it is missing, `type` becomes an empty string.
  
  const payload = type.includes('application/json') ? await response.json() : null; // If the server sent JSON, parse it into a JavaScript object. Otherwise, `payload` is `null`.
  // For a successful customer creation, Django returns JSON containing the customer. If Django returns a JSON error, such as a duplicate customer name, that response is parsed here too.

  // `response.ok` is true for HTTP success statuses such as `200` or `201`.
  // If the request failed, the helper throws an error using Django’s `detail` message when available. Otherwise, it uses the generic message.
  //  In `NewCustomer`, the `catch` block receives that error and displays it.
  if (!response.ok) throw new Error(payload?.detail || 'The request could not be completed.');
  return payload;

  // On success, return the parsed JSON to the caller. `NewCustomer` doesn’t need the returned customer data, so it just waits for success and then navigates to `/inventions`.
  // So this function handles the **request mechanics**—headers, CSRF token, cookies, JSON parsing, and errors—while `NewCustomer` handles the **customer form and what to do after the response**.
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
