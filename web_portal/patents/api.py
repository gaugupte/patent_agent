import json
import logging
from pathlib import Path
from time import monotonic
from urllib.parse import unquote

import httpx
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.http import FileResponse, Http404, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.api import _json_body, portal_login_required
from .models import Customer, Invention, InventionVersion


logger = logging.getLogger(__name__)


def _customer_json(customer):
    return {"id": customer.pk, "name": customer.name}


def _version_json(version):
    return {
        "id": str(version.pk),
        "number": version.number,
        "status": version.status,
        "created_at": version.created_at.isoformat(),
        "completed_at": version.completed_at.isoformat() if version.completed_at else None,
        "idf_filename": version.idf_filename,
        "has_report": bool(version.report_path),
        "error_message": version.error_message,
        "analysis_result": version.analysis_result,
    }


def _invention_json(invention, include_versions=False):
    result = {
        "id": invention.pk,
        "invention_number": invention.invention_number,
        "title": invention.title,
        "customer": _customer_json(invention.customer),
        "created_at": invention.created_at.isoformat(),
        "latest_status": None,
        "latest_version": None,
    }
    versions = list(invention.versions.all())
    if versions:
        result["latest_status"] = versions[0].status
        result["latest_version"] = versions[0].number
    if include_versions:
        result["versions"] = [_version_json(version) for version in versions]
    return result


def _validate_upload(upload):
    if upload is None:
        return "Choose an IDF text file to upload."
    if Path(upload.name).suffix.lower() != ".txt":
        return "For v1, IDFs must be uploaded as .txt files encoded as UTF-8."
    if upload.size > settings.IDF_MAX_BYTES:
        return f"The IDF must be smaller than {settings.IDF_MAX_BYTES // (1024 * 1024)} MB."
    try:
        upload.read().decode("utf-8")
        upload.seek(0)
    except (UnicodeDecodeError, AttributeError):
        upload.seek(0)
        return "The IDF text file must use UTF-8 encoding."
    return None


def _run_analysis(version):
    version.status = InventionVersion.Status.PROCESSING
    version.error_message = ""
    version.save(update_fields=["status", "error_message"])

    started_at = monotonic()
    logger.info(
        "Starting FastAPI analysis for version %s (read timeout %.0f seconds)",
        version.pk,
        settings.FASTAPI_TIMEOUT_SECONDS,
    )
    try:
        with version.idf_file.open("rb") as idf_stream:
            response = httpx.post(
                settings.FASTAPI_PREDICT_URL,
                data={"session_id": str(version.pk)},
                files={"idf_file": (version.idf_filename, idf_stream, "text/plain; charset=utf-8")},
                timeout=settings.FASTAPI_TIMEOUT_SECONDS,
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("The analysis service returned an unexpected response.")

        report_path = str(payload.pop("report_path", "") or "")
        # The uploaded IDF and thread identifier are kept out of the JSON result.
        payload.pop("idf_text", None)
        payload.pop("session_id", None)
        version.analysis_result = payload
        version.report_path = report_path
        version.status = InventionVersion.Status.COMPLETED
        version.completed_at = timezone.now()
        version.save(
            update_fields=["analysis_result", "report_path", "status", "completed_at", "error_message"]
        )
        logger.info(
            "FastAPI analysis completed for version %s in %.1f seconds",
            version.pk,
            monotonic() - started_at,
        )
        return True
    except (httpx.HTTPError, ValueError, OSError):
        logger.exception(
            "Analysis request failed for version %s after %.1f seconds",
            version.pk,
            monotonic() - started_at,
        )
        version.status = InventionVersion.Status.FAILED
        version.error_message = "Analysis failed. Please try again or contact support."
        version.save(update_fields=["status", "error_message"])
        return False


def _create_version(invention, upload, version_number):
    version = InventionVersion(invention=invention, number=version_number)
    version.idf_file.save(Path(upload.name).name, ContentFile(upload.read()), save=False)
    version.save()
    return version


@require_GET
@portal_login_required
def customers(request):
    items = Customer.objects.filter(organization=request.user.organization).order_by("name")
    return JsonResponse({"customers": [_customer_json(item) for item in items]})


@require_POST
@portal_login_required
def create_customer(request):
    body = _json_body(request)
    if body is None:
        return JsonResponse({"detail": "Invalid request body."}, status=400)
    name = str(body.get("name", "")).strip()
    if not name or len(name) > 160:
        return JsonResponse({"detail": "Enter a customer name up to 160 characters."}, status=400)
    try:
        customer = Customer.objects.create(organization=request.user.organization, name=name)
    except IntegrityError:
        return JsonResponse({"detail": "A customer with that name already exists in your organization."}, status=409)
    return JsonResponse({"customer": _customer_json(customer)}, status=201)


@require_GET
@portal_login_required
def inventions(request):
    customer_id = request.GET.get("customer_id")
    customer_qs = Customer.objects.filter(organization=request.user.organization)
    if customer_id:
        customer = customer_qs.filter(pk=customer_id).first()
        if customer is None:
            return JsonResponse({"detail": "Customer not found."}, status=404)
    else:
        customer = customer_qs.first()
    if customer is None:
        return JsonResponse({"inventions": [], "customer": None})
    qs = Invention.objects.filter(customer=customer).select_related("customer").prefetch_related("versions")
    return JsonResponse(
        {"customer": _customer_json(customer), "inventions": [_invention_json(item) for item in qs]}
    )


@require_POST
@portal_login_required
def create_invention(request):
    customer_id = request.POST.get("customer_id", "")
    title = request.POST.get("title", "").strip()
    upload = request.FILES.get("idf_file")
    customer = Customer.objects.filter(pk=customer_id, organization=request.user.organization).first()
    if customer is None:
        return JsonResponse({"detail": "Choose a customer belonging to your organization."}, status=400)
    if not title or len(title) > 20:
        return JsonResponse({"detail": "Enter an invention title up to 20 characters."}, status=400)
    upload_error = _validate_upload(upload)
    if upload_error:
        return JsonResponse({"detail": upload_error}, status=400)

    with transaction.atomic():
        invention = Invention.objects.create(customer=customer, title=title, created_by=request.user)
        version = _create_version(invention, upload, 1)
    succeeded = _run_analysis(version)
    body = {
        "invention": _invention_json(invention, include_versions=True),
        "analysis_succeeded": succeeded,
    }
    # The invention/version is saved even if the separate analysis service is
    # temporarily unavailable. Return the created record so the UI can show
    # its failed status and allow a later version to be submitted.
    return JsonResponse(body, status=201)


@require_GET
@portal_login_required
def invention_detail(request, invention_id):
    invention = (
        Invention.objects.filter(
            pk=invention_id,
            customer__organization=request.user.organization,
        )
        .select_related("customer")
        .prefetch_related("versions")
        .first()
    )
    if invention is None:
        return JsonResponse({"detail": "Invention not found."}, status=404)
    return JsonResponse({"invention": _invention_json(invention, include_versions=True)})


@require_POST
@portal_login_required
def add_version(request, invention_id):
    invention = (
        Invention.objects.filter(pk=invention_id, customer__organization=request.user.organization)
        .select_related("customer")
        .first()
    )
    if invention is None:
        return JsonResponse({"detail": "Invention not found."}, status=404)
    upload_error = _validate_upload(request.FILES.get("idf_file"))
    if upload_error:
        return JsonResponse({"detail": upload_error}, status=400)

    with transaction.atomic():
        locked = Invention.objects.select_for_update().get(pk=invention.pk)
        latest = locked.versions.order_by("-number").values_list("number", flat=True).first() or 0
        version = _create_version(locked, request.FILES["idf_file"], latest + 1)
    _run_analysis(version)
    version.refresh_from_db()
    return JsonResponse(
        {"version": _version_json(version)},
        status=201,
    )


@require_GET
@portal_login_required
def download_report(request, version_id):
    version = (
        InventionVersion.objects.filter(
            pk=version_id,
            invention__customer__organization=request.user.organization,
            status=InventionVersion.Status.COMPLETED,
        )
        .select_related("invention")
        .first()
    )
    if version is None or not version.report_path:
        raise Http404("Report not found.")

    candidate = Path(unquote(version.report_path))
    if not candidate.is_absolute():
        candidate = settings.REPOSITORY_ROOT / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(settings.FASTAPI_REPORT_ROOT)
    except ValueError:
        raise Http404("Report not found.")
    if not candidate.is_file():
        raise Http404("Report not found.")

    filename = f"{version.invention.invention_number}-analysis-v{version.number}.docx"
    return FileResponse(candidate.open("rb"), as_attachment=True, filename=filename)
