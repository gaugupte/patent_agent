# Google and email sign-in setup

The portal supports two ways to sign in:

- **Google:** OpenID Connect authorization-code flow. Django validates Google's ID token and uses the verified email to find or create the portal profile. A new user gets a personal workspace. The Google identity is then stored by its issuer and stable subject ID.
- **Email code:** Django sends a six-digit code that expires in ten minutes. A new verified email gets a personal workspace; a code sent to an existing portal email signs in that existing account. The code is stored as a password hash and is limited to five attempts. Requests are throttled by email and IP.

Both methods end in a normal Django session and `sessionid` cookie. React does not store provider tokens.

## Apply the database migration

From the project root, with the virtual environment activated:

```powershell
python -m pip install google-auth==2.62.0
python web_portal/manage.py migrate
```

The migration creates `accounts_externalidentity` for Google identity links and `accounts_emaillogincode` for temporary email challenges.

## Configure Google sign-in

1. In Google Cloud Console, create an OAuth client with application type **Web application** and configure the OAuth consent screen.
   While the consent screen is in testing mode, only accounts listed as test users can sign in; move it to production when ready to open it to other Google accounts.
2. Add this development redirect URI to the client (it must match exactly):

   ```text
   http://127.0.0.1:8001/api/auth/google/callback/
   ```

3. In this working copy, open `web_portal/portal_config/local_auth.py` in your editor and replace the blank client ID and secret values. For a fresh checkout, first copy `local_auth.example.py` to `local_auth.py`. Keep the secret private; the local file is excluded from Git and must not be added to React.

   The template already has the correct local redirect URI and React URL; leave those as shown unless your ports differ.

Google is asked only for `openid`, `email`, and `profile`; the app does not request Gmail or Drive access. Google-provided verified email, first name, and last name populate the portal profile. In production, use the HTTPS callback URL and frontend URL for your deployed domain, and register that callback in Google Cloud Console.

## Configure email-code delivery

For local development, the current default is Django's console email backend: the code is printed in the Django terminal. To deliver real email, configure SMTP environment variables before starting Django:

```powershell
$env:DJANGO_EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
$env:EMAIL_HOST = "smtp.example.com"
$env:EMAIL_PORT = "587"
$env:EMAIL_HOST_USER = "your-smtp-user"
$env:EMAIL_HOST_PASSWORD = "your-smtp-password"
$env:EMAIL_USE_TLS = "true"
$env:DEFAULT_FROM_EMAIL = "PatentDesk <noreply@your-domain.com>"
```

Use the credentials and verified sender domain from your chosen email delivery provider. Configure the values as protected environment secrets in deployment. Email verification confirms mailbox access; it does not assign someone to a client organization. New self-signups start in personal workspaces. Organization accounts remain attached to the organization already assigned to their portal profile.

## Start the portal

After the migration and environment configuration, start Django and React as usual. Google sign-in uses the callback route on Django; Django redirects back to the configured frontend URL after it creates the session.
