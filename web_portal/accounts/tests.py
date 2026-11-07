# Account endpoint tests use the Django test client and pytest-django database fixtures.
import json
from datetime import timedelta

import pytest
from django.contrib.auth.hashers import make_password
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import ActivePortalSession, EmailLoginCode, PortalUser

"""
`client` is provided by **pytest-django**, not defined in your project files. It’s a Django test client fixture that sends 
requests to your app without running a server.

Your `authenticated_client` fixture in [web_portal/conftest.py](E:/Gautam/work_folder/own/nlp/patent_agent/web_portal/conftest.py)
uses it, signs in through the login endpoint, then returns the signed-in client. The tests request `client` directly when they need an unauthenticated client.
Right—both `client` and `authenticated_client` are used across the tests.

- **`client`** is pytest-django’s built-in fixture. It provides a fresh, unauthenticated Django test client for each test that requests it. Tests use it to make requests as a visitor or to test login flows.
- **`authenticated_client`** is our project fixture in [web_portal/conftest.py](E:/Gautam/work_folder/own/nlp/patent_agent/web_portal/conftest.py). It uses `client`, signs in a test user, and returns that same client with the logged-in session.

For example, the health test uses `client` to check the public endpoint. The customer access tests use `authenticated_client` to make requests as a signed-in user.
"""


def post_json(client, url, payload):
    # Encode a Python object as the JSON request body expected by the API endpoints.
    return client.post(url, data=json.dumps(payload), content_type="application/json")


# Health checks are intentionally available without an authenticated session.
def test_health_endpoint_is_public(client):
    # reverse("api-health") looks up the URL pattern named "api-health" and returns its path, such as /api/health/.
    # Then client.get(...) sends a GET request to that path using Django’s test client. No hardcoding
    response = client.get(reverse("api-health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# Successful login should establish one active session and expose the current user.
def test_sign_in_creates_the_only_active_portal_session(client, portal_user):
    response = post_json(
        client,
        reverse("portal-login"),
        {"username": " member01 ", "password": "Correct-Horse-42!"},
    )

    assert response.status_code == 200
    assert response.json()["username"] == "member01"
    assert response.json()["access_active"] is True
    assert ActivePortalSession.objects.filter(user=portal_user).count() == 1

    current = client.get(reverse("portal-current-user"))
    assert current.status_code == 200
    assert current.json()["organization"]["name"] == "Example Org"


# Enforce the one-browser-at-a-time session rule for a user account.
def test_second_browser_cannot_sign_in_until_first_signs_out(client, portal_user):
    payload = {"username": "member01", "password": "Correct-Horse-42!"}
    first_response = post_json(client, reverse("portal-login"), payload)
    second_response = post_json(Client(), reverse("portal-login"), payload)

    assert first_response.status_code == 200
    assert second_response.status_code == 409


# Bad credentials must fail without creating a server-side active session.
def test_invalid_credentials_do_not_create_a_session(client, portal_user):
    response = post_json(
        client,
        reverse("portal-login"),
        {"username": "member01", "password": "wrong"},
    )

    assert response.status_code == 400
    assert not ActivePortalSession.objects.filter(user=portal_user).exists()


# Invalid JSON should return a controlled client error rather than an exception.
def test_malformed_login_json_is_rejected(client):
    response = client.post(reverse("portal-login"), data="{", content_type="application/json")

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid request body."


# A user belonging to a disabled organization must not be allowed to sign in.
def test_inactive_organization_cannot_sign_in(client, organization, portal_user):
    organization.is_active = False
    organization.save(update_fields=["is_active"])

    response = post_json(
        client,
        reverse("portal-login"),
        {"username": "member01", "password": "Correct-Horse-42!"},
    )

    assert response.status_code == 403
    assert not ActivePortalSession.objects.filter(user=portal_user).exists()


# Verification codes are stored hashed, consumed after success, and cannot be replayed.
def test_email_code_is_single_use_and_stored_as_a_hash(client, portal_user):
    code = "123456"
    challenge = EmailLoginCode.objects.create(
        email=portal_user.email,
        code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(minutes=10),
    )

    response = post_json(
        client,
        reverse("email-code-verify"),
        {"email": portal_user.email, "code": code},
    )

    assert response.status_code == 200
    challenge.refresh_from_db()
    assert challenge.consumed_at is not None
    assert challenge.code_hash != code
    assert client.get(reverse("portal-current-user")).status_code == 200

    replay = post_json(
        Client(),
        reverse("email-code-verify"),
        {"email": portal_user.email, "code": code},
    )
    assert replay.status_code == 400


# Expired codes must not authenticate a user or create an active session.
def test_expired_email_code_is_rejected(client, portal_user):
    EmailLoginCode.objects.create(
        email=portal_user.email,
        code_hash=make_password("123456"),
        expires_at=timezone.now() - timedelta(seconds=1),
    )

    response = post_json(
        client,
        reverse("email-code-verify"),
        {"email": portal_user.email, "code": "123456"},
    )

    assert response.status_code == 400
    assert not ActivePortalSession.objects.filter(user=portal_user).exists()


# Logout removes the active server-side session and protects subsequent requests.
def test_sign_out_revokes_the_active_session(client, portal_user):
    signed_in = post_json(
        client,
        reverse("portal-login"),
        {"username": "member01", "password": "Correct-Horse-42!"},
    )
    assert signed_in.status_code == 200

    response = client.post(reverse("portal-logout"))

    assert response.status_code == 200
    assert not ActivePortalSession.objects.filter(user=portal_user).exists()
    assert client.get(reverse("portal-current-user")).status_code == 401
