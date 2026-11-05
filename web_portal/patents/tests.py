import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from patents.models import Customer, Invention


def test_protected_customer_endpoint_rejects_anonymous_user(client):
    response = client.get(reverse("customers"))

    assert response.status_code == 401


def test_customer_list_contains_only_current_organizations_customers(authenticated_client, customer):
    response = authenticated_client.get(reverse("customers"))

    assert response.status_code == 200
    assert [item["name"] for item in response.json()["customers"]] == [customer.name]
    assert "Customer B" not in response.content.decode()


def test_expired_trial_cannot_access_customer_data(authenticated_client, portal_user):
    portal_user.trial_ends_at = timezone.now() - timedelta(seconds=1)
    portal_user.save(update_fields=["trial_ends_at"])

    response = authenticated_client.get(reverse("customers"))

    assert response.status_code == 403
    assert "trial has ended" in response.json()["detail"]


def test_duplicate_customer_name_is_rejected_without_duplicate_row(
    authenticated_client, organization, customer
):
    response = authenticated_client.post(
        reverse("customer-create"),
        data=json.dumps({"name": " Customer A "}),
        content_type="application/json",
    )

    assert response.status_code == 409
    assert Customer.objects.filter(organization=organization, name="Customer A").count() == 1


def test_cannot_create_invention_for_another_organizations_customer(authenticated_client, other_customer):
    response = authenticated_client.post(
        reverse("invention-create"),
        {"customer_id": other_customer.pk, "title": "Private", "idf_file": upload("spec.txt")},
    )

    assert response.status_code == 400
    assert Invention.objects.count() == 0


def test_non_text_upload_is_rejected_before_analysis(authenticated_client, customer):
    with patch("patents.api._run_analysis") as analyze:
        response = authenticated_client.post(
            reverse("invention-create"),
            {"customer_id": customer.pk, "title": "New invention", "idf_file": upload("spec.pdf")},
        )

    assert response.status_code == 400
    assert Invention.objects.count() == 0
    analyze.assert_not_called()


def test_non_utf8_text_upload_is_rejected(authenticated_client, customer):
    invalid_upload = upload("spec.txt", b"\xff\xfe")

    response = authenticated_client.post(
        reverse("invention-create"),
        {"customer_id": customer.pk, "title": "New invention", "idf_file": invalid_upload},
    )

    assert response.status_code == 400
    assert "UTF-8" in response.json()["detail"]
    assert Invention.objects.count() == 0


@pytest.mark.parametrize("content", [b"12345", b"123456789"])
def test_upload_above_configured_size_limit_is_rejected(
    authenticated_client, customer, settings, content
):
    settings.IDF_MAX_BYTES = 4

    response = authenticated_client.post(
        reverse("invention-create"),
        {"customer_id": customer.pk, "title": "New invention", "idf_file": upload("spec.txt", content)},
    )

    assert response.status_code == 400
    assert "smaller than" in response.json()["detail"]
    assert Invention.objects.count() == 0


def test_valid_idf_is_saved_and_sent_to_analysis(authenticated_client, customer):
    with patch("patents.api._run_analysis", return_value=True) as analyze:
        response = authenticated_client.post(
            reverse("invention-create"),
            {
                "customer_id": customer.pk,
                "title": "New invention",
                "idf_file": upload("spec.txt", b"Invention title: Example\n"),
            },
        )

    assert response.status_code == 201
    assert response.json()["analysis_succeeded"] is True
    assert Invention.objects.count() == 1
    version = Invention.objects.get().versions.get()
    assert version.idf_filename == "spec.txt"
    assert version.idf_file.storage.exists(version.idf_file.name)
    analyze.assert_called_once_with(version)


def test_invention_detail_does_not_disclose_another_organization(authenticated_client, other_customer):
    other_invention = Invention.objects.create(customer=other_customer, title="Secret")

    response = authenticated_client.get(reverse("invention-detail", args=[other_invention.pk]))

    assert response.status_code == 404


def upload(name, content=b"Valid UTF-8 IDF content\n"):
    return SimpleUploadedFile(name, content, content_type="text/plain")
