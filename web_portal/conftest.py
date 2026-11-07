# Shared fixtures here are available to tests throughout web_portal.
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import Organization, PortalUser
from patents.models import Customer


@pytest.fixture(autouse=True)
def fast_password_hasher(settings):
    # Use a deliberately fast hasher in tests; production keeps its secure hasher.
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def organization(db):
    # Create a default tenant; requesting this fixture also enables database access.
    return Organization.objects.create(
        name="Example Org",
        access_type=Organization.AccessType.ORGANIZATION,
    )


@pytest.fixture
def other_organization(db):
    # A second tenant lets tests verify that records stay isolated between tenants.
    return Organization.objects.create(name="Other Org")


@pytest.fixture
def portal_user(organization):
    # Create a normal user in the default tenant with a valid trial period.
    return PortalUser.objects.create_user(
        username="member01",
        email="member@example.com",
        password="Correct-Horse-42!",
        organization=organization,
        trial_ends_at=timezone.now() + timedelta(days=7),
    )


@pytest.fixture
def authenticated_client(client, portal_user):
    # Sign in through the real endpoint so tests exercise session setup as well.
    response = client.post(
        reverse("portal-login"),
        data='{"username":"member01","password":"Correct-Horse-42!"}',
        content_type="application/json",
    )
    assert response.status_code == 200
    # Return the logged-in client for use in protected endpoint tests.
    return client


@pytest.fixture
def customer(db, organization):
    # Provide a customer owned by the default tenant.
    return Customer.objects.create(organization=organization, name="Customer A")


@pytest.fixture
def other_customer(db, other_organization):
    # Provide a customer owned by the second tenant for access-control tests.
    return Customer.objects.create(organization=other_organization, name="Customer B")
