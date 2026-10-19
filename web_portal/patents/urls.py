from django.urls import path

from . import api


urlpatterns = [
    path("customers/", api.customers, name="customers"),
    path("customers/create/", api.create_customer, name="customer-create"),
    path("inventions/", api.inventions, name="inventions"),
    path("inventions/create/", api.create_invention, name="invention-create"),
    path("inventions/<int:invention_id>/", api.invention_detail, name="invention-detail"),
    path("inventions/<int:invention_id>/versions/", api.add_version, name="invention-add-version"),
    path("versions/<uuid:version_id>/report/", api.download_report, name="version-report"),
]
