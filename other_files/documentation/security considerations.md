# Portal browser and database security

This note records where the portal handles CSRF, CORS, XSS, and SQL injection.

## CSRF

- Django's `CsrfViewMiddleware` is enabled in `web_portal/portal_config/settings.py`.
- `web_portal/frontend/src/api.js` obtains a masked CSRF token from `/api/csrf/` and sends it in `X-CSRFToken` for every unsafe method.
- The session cookie is HttpOnly and SameSite Lax. The CSRF cookie is also HttpOnly; React uses the token returned in the JSON response rather than reading the cookie.
- Production cookies are Secure, and Django trusts only explicitly configured CSRF origins (`CSRF_TRUSTED_ORIGINS`).

## CORS

The portal does not enable cross-origin API access. The Vite development server proxies `/api` through its own origin, and the production Nginx configuration serves React and proxies Django under one origin. With no `Access-Control-Allow-Origin` response header, browsers block JavaScript on other origins from reading API responses. Keep this same-origin arrangement; do not add `*` CORS access alongside credentialed session cookies.

If a future deployment intentionally serves the UI and API from separate origins, add a narrow explicit origin allowlist and credentials policy, and update CSRF trusted origins and cookie settings together.

## XSS

- React renders user and analysis text as normal JSX children, which React escapes. The frontend currently has no `dangerouslySetInnerHTML` use.
- The production UI CSP is in `web_portal/nginx.conf.example`: scripts, styles, API connections, and assets are restricted to the app's own origin; plugins/objects and framing are blocked.
- Do not render uploaded files or model-generated strings as HTML. If rich HTML is introduced, sanitize it with an allowlist before rendering and review the CSP impact.
- Django also sets `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, a restrictive referrer policy, and same-origin opener policy.

## SQL injection

Portal database access uses Django ORM filters, creates, and updates. These bind values as query parameters. Keep using ORM query methods and never interpolate user input into SQL strings. If raw SQL becomes necessary, use Django's parameterized `cursor.execute(sql, params)` form.

## HTTPS deployment

When `DJANGO_DEBUG=false`, Django marks session and CSRF cookies Secure, redirects to HTTPS by default, and emits HSTS for one year. The Nginx example has an HTTP-to-HTTPS redirect and a TLS server block; replace its certificate paths for deployment. Nginx sends `X-Forwarded-Proto` to Django, and `SECURE_PROXY_SSL_HEADER` trusts that proxy header. If a load balancer terminates TLS before Nginx, configure the trusted proxy chain to preserve the HTTPS scheme instead of relying on Nginx's local HTTP scheme. Only set `SECURE_SSL_REDIRECT=false` if HTTPS redirects are handled safely by the trusted ingress instead. Do not expose Django's upstream port publicly.
