

django default:

MVT:
    model: for database defintion and CRUD actionS
    view: for writing actual functions. Functions actual has the server logic. ex submission of form, checking of logic, callind db function/objecs
    Templates: html files with html + block of cody for dynamic content

`web_portal/` is the new portal layer. It adds the React interface and Django services while leaving the existing FastAPI analysis app at the project root.

```text
web_portal/
├── frontend/       React interface and Vite development server
├── accounts/       Organizations, portal users, sign-in, password reset
├── patents/        Customers, inventions, versions, analysis and reports
├── portal_config/  Django settings, URLs, and server entry points
├── templates/      Password reset email templates
├── manage.py       Django commands
├── requirements.txt
└── nginx.conf.example
```

### How the parts fit together

- **`frontend/`** contains the screens and browser code. `main.jsx` handles the pages and navigation, `api.js` makes requests to Django, and `styles.css` contains the styling. In development, Vite proxies `/api` requests to Django.
- **`accounts/`** defines organizations and users, plus sign-in and password reset. Admin users create organizations and assign portal users to them; there’s no public signup.
- **`patents/`** contains the customer, invention, and invention-version records. Its API checks the signed-in user’s organization when listing or accessing data.
- **`portal_config/`** is Django’s project configuration: database selection, security settings, and routes connecting URLs to the account and patent APIs.
- **`migrations/`** records Django’s database schema changes. Django applies these with `manage.py migrate`; SQLite is the default, and `DATABASE_URL` can select PostgreSQL.
- **`templates/`** holds the email text and HTML used for password-reset links.

### What happens when someone submits an IDF

The React page sends the upload to Django. Django stores it as an invention version, calls the existing FastAPI `/predict` endpoint, and saves the analysis result. When a user downloads a report, Django checks that the invention belongs to their organization before serving it.

In local development, React runs on port **5173**, Django on **8001**, and FastAPI on **8000**. In production, Nginx serves React and proxies portal requests to Django; Django calls FastAPI privately. The configuration example is in [nginx.conf.example](</E:/Gautam/work_folder/own/nlp/patent_agent/web_portal/nginx.conf.example>).


The separation is visible in **`web_portal/frontend/`** versus the Django folders beside it:

```text
web_portal/
├── frontend/           React code
│   └── src/
│       ├── main.jsx    Screens and browser navigation
│       ├── api.js      HTTP requests to Django
│       └── styles.css  Browser styling
├── accounts/           Django app: users, organizations, authentication
├── patents/            Django app: customers, inventions, analysis APIs
└── portal_config/      Django settings and URL routing
```

React runs in the browser. For example, `main.jsx` calls `api()` in `api.js`; it doesn’t import Django code or talk to the database.

Django receives those HTTP requests. Its URLs in `portal_config/urls.py` route `/api/auth/...` to `accounts/api.py` and other `/api/...` requests to `patents/api.py`. Those Python files handle authentication and database operations.

In development, Vite serves React on port **5173** and forwards `/api` requests to Django on port **8001**, as configured in `frontend/vite.config.js`. In production, Nginx serves the built React files and forwards `/api/` requests to Django. The browser still talks to one site, but React’s files and Django’s Python code are built and run separately.

==================================================================================================================================================


Here’s the frontend flow from opening the page to viewing an analysis.

### 1. React starts

[**index.html**](</E:/Gautam/work_folder/own/nlp/patent_agent/web_portal/frontend/index.html>) has an empty `<div id="root">`. The React app mounts into it from the bottom of [**main.jsx**](</E:/Gautam/work_folder/own/nlp/patent_agent/web_portal/frontend/src/main.jsx:128>).

Inside `main.jsx`, the app is wrapped in:

- `BrowserRouter`, which maps browser URLs to screens.
- `AuthProvider`, which checks whether a user already has a session by requesting `/api/auth/me/`.

### 2. The route decides which screen to show

`RoutesRoot` maps URLs to pages:

- `/login` → sign-in
- `/inventions` → the customer’s invention list
- `/inventions/new` → create an invention
- `/inventions/:id` → invention details and analysis versions
- `/customers/new` → add a customer
- `/help` → help page

The invention and customer pages are protected. `Protected` waits for the session check; if there’s no signed-in user, it sends the browser to `/login`. Signed-in users see the shared navigation and organization name from `Shell`.

### 3. A page calls Django through `api.js`

For example, the inventions page requests the customer list, then requests inventions for the selected customer.

`api.js` adds the `/api` prefix to requests. So this:

```js
api('/customers/')
```

becomes a browser request to:

```text
/api/customers/
```

In development, [**vite.config.js**](</E:/Gautam/work_folder/own/nlp/patent_agent/web_portal/frontend/vite.config.js>) forwards `/api` requests from React on port `5173` to Django on port `8001`. React does not connect directly to the database or FastAPI.

### 4. Sign-in and protected requests

The sign-in page sends the username and password to Django. For requests that change data, `api.js` first fetches a CSRF token, then sends it with the request. Django handles the session cookie and returns the signed-in user’s information.

The route flow is:

```text
Browser URL → React route → page component → api.js → Django API
```

### 5. Creating and viewing an invention

When you submit a new invention, the page sends the customer, title, and `.txt` IDF file to Django as a form upload. Django saves the invention version, calls FastAPI for analysis, and returns the result. The browser then opens the invention’s detail page.

That page loads the invention and its versions. It can also submit a revised IDF as another version or request a report download. Django checks that the user’s organization is allowed to access the invention before returning data or a report.

So, React handles **what the user sees and does**; Django handles **accounts, permissions, records, and calls to FastAPI**.


==================================================================================================================================================

Here’s the flow in the order it runs, starting from opening `http://127.0.0.1:5173/`.

## 1. Vite serves the app’s entry page

The Vite development server returns [**index.html**](</E:/Gautam/work_folder/own/nlp/patent_agent/web_portal/frontend/index.html:9>). Its `<div id="root">` is an empty container, and its script tag loads `/src/main.jsx`.

At this point, the browser has loaded the React app’s code. Vite is serving files; it hasn’t sent the user’s credentials or invention data to Django.

## 2. `main.jsx` mounts React and sets up routing

At the bottom of [**main.jsx**](</E:/Gautam/work_folder/own/nlp/patent_agent/web_portal/frontend/src/main.jsx:128>), `createRoot(...).render(...)` mounts React into that `root` element. The app is wrapped in three layers:

- `BrowserRouter` watches the browser URL and lets React navigate between pages.
- `AuthProvider` stores the current user’s sign-in state.
- `RoutesRoot` chooses which page component to display for the current URL.

The URL-to-page choices are in `RoutesRoot` at [**main.jsx**](</E:/Gautam/work_folder/own/nlp/patent_agent/web_portal/frontend/src/main.jsx:126>).

## 3. The first Django request checks for an existing session

When `AuthProvider` mounts, its `useEffect` calls `refresh()` at [**main.jsx**](</E:/Gautam/work_folder/own/nlp/patent_agent/web_portal/frontend/src/main.jsx:11>). `refresh()` makes this request:

```text
GET /api/auth/me/
```

The actual frontend call is `api('/auth/me/')`. [**api.js**](</E:/Gautam/work_folder/own/nlp/patent_agent/web_portal/frontend/src/api.js:7>) prepends `/api`, includes browser cookies, and sends the request.

The path gets to Django in two routing steps:

1. In [**vite.config.js**](</E:/Gautam/work_folder/own/nlp/patent_agent/web_portal/frontend/vite.config.js:9>), Vite proxies requests beginning with `/api` to `http://127.0.0.1:8001`.
2. In [**portal_config/urls.py**](</E:/Gautam/work_folder/own/nlp/patent_agent/web_portal/portal_config/urls.py:11>), Django sends `/api/auth/` routes to `accounts/urls.py`. Its `me/` route calls `accounts.api.current_user`.

If Django recognizes a signed-in portal user, it returns their username, email, and organization. React stores that in `AuthProvider`. If there’s no valid session, Django returns an unauthenticated response; `refresh()` catches it and sets the user to `null`.

While the initial check is pending, `user` is `undefined`. `Protected` shows “Loading your workspace…” until the check finishes. Afterward, a signed-in user can enter protected pages; an unsigned user gets sent to `/login`.

## 4. What happens when you submit the login form

`Login` holds the username, password, error, and busy/loading state. When you submit the form, its handler at [**main.jsx**](</E:/Gautam/work_folder/own/nlp/patent_agent/web_portal/frontend/src/main.jsx:54>) calls:

```text
POST /api/auth/login/
```

Because this changes server state, `api.js` first calls `csrf()`, which sends `GET /api/csrf/`. Django’s `csrf_token` view sets a CSRF cookie and returns a token. Then `api.js` sends the login request with:

- A JSON body containing the username and password.
- The CSRF token in the `X-CSRFToken` header.
- `credentials: 'include'`, so the browser sends and receives Django session cookies.

Vite proxies this POST to Django. Django routes it through `portal_config/urls.py` and `accounts/urls.py` to `accounts.api.sign_in`. That function parses the JSON, authenticates the username and password, checks the organization, and—if valid—creates a Django login session.

A regular portal user gets a success response with their user and organization details. React saves that response with `setUser(...)` and navigates to `/inventions`. The admin superuser is deliberately directed to use `/admin/` instead.

## 5. What happens when the inventions screen opens

On `/inventions`, the `Inventions` component makes a GET request for customers. After the response arrives, it saves the list in React state and selects the first customer. That selection triggers a second effect, which requests inventions for that customer.

The general pattern is:

```text
React page event or effect
    → api.js
    → browser request to /api/...
    → Vite proxy to Django
    → Django URL route and view
    → JSON response
    → React state update
    → page rerenders with the new state
```

For example, selecting a different customer changes React state; that causes the inventions request to run again with the new customer ID.

## 6. Creating an invention adds FastAPI to the flow

On `/inventions/new`, the page loads the organization’s customer list. When you submit the form, it packages the customer ID, title, and `.txt` file in `FormData`. The browser sends that to:

```text
POST /api/inventions/create/
```

`api.js` recognizes `FormData` and leaves the multipart content type to the browser. Vite proxies the request to Django. Django validates the upload, creates the invention and version records, saves the file, and then Django calls FastAPI’s `/predict` endpoint.

So **React does not call FastAPI directly**. For analysis, the path is:

```text
React → Django → FastAPI → Django → React
```

Django returns the created invention and analysis status. React then navigates to the invention details page.

## 7. Viewing a detail page and downloading a report

The detail page requests:

```text
GET /api/inventions/<id>/
```

Django returns that invention’s versions and results after checking the user’s organization. React displays the versions and renders the analysis JSON.

When you upload a revised IDF, React sends it to the invention’s versions endpoint. Django saves it as the next version and calls FastAPI again.

For report downloads, `downloadReport()` in [**api.js**](</E:/Gautam/work_folder/own/nlp/patent_agent/web_portal/frontend/src/api.js:20>) fetches the report endpoint. Django checks that the user’s organization owns the invention before returning the file.

One development detail: `main.jsx` wraps the app in `React.StrictMode`. In development, React may run mount effects twice to help expose bugs, so you might see duplicate initial GET requests in the browser’s Network panel. That’s a development behavior; it doesn’t mean two inventions or customers are being created.