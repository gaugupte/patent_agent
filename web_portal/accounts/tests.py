import json
from datetime import timedelta

import pytest
from django.contrib.auth.hashers import make_password
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import ActivePortalSession, EmailLoginCode, PortalUser


def post_json(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type="application/json")


def test_health_endpoint_is_public(client):
    response = client.get(reverse("api-health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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


def test_second_browser_cannot_sign_in_until_first_signs_out(client, portal_user):
    payload = {"username": "member01", "password": "Correct-Horse-42!"}
    first_response = post_json(client, reverse("portal-login"), payload)
    second_response = post_json(Client(), reverse("portal-login"), payload)

    assert first_response.status_code == 200
    assert second_response.status_code == 409


def test_invalid_credentials_do_not_create_a_session(client, portal_user):
    response = post_json(
        client,
        reverse("portal-login"),
        {"username": "member01", "password": "wrong"},
    )

    assert response.status_code == 400
    assert not ActivePortalSession.objects.filter(user=portal_user).exists()


def test_malformed_login_json_is_rejected(client):
    response = client.post(reverse("portal-login"), data="{", content_type="application/json")

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid request body."


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
