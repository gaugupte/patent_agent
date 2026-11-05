from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import Organization, PortalUser
from patents.models import Customer


@pytest.fixture(autouse=True)
def fast_password_hasher(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def organization(db):
    return Organization.objects.create(
        name="Example Org",
        access_type=Organization.AccessType.ORGANIZATION,
    )


@pytest.fixture
def other_organization(db):
    return Organization.objects.create(name="Other Org")


@pytest.fixture
def portal_user(organization):
    return PortalUser.objects.create_user(
        username="member01",
        email="member@example.com",
        password="Correct-Horse-42!",
        organization=organization,
        trial_ends_at=timezone.now() + timedelta(days=7),
    )


@pytest.fixture
def authenticated_client(client, portal_user):
    response = client.post(
        reverse("portal-login"),
        data='{"username":"member01","password":"Correct-Horse-42!"}',
        content_type="application/json",
    )
    assert response.status_code == 200
    return client


@pytest.fixture
def customer(db, organization):
    return Customer.objects.create(organization=organization, name="Customer A")


@pytest.fixture
def other_customer(db, other_organization):
    return Customer.objects.create(organization=other_organization, name="Customer B")
