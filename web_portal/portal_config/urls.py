from django.contrib import admin
from django.urls import include, path

from accounts import api as account_api


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", account_api.health, name="api-health"),
    path("api/csrf/", account_api.csrf_token, name="api-csrf"),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("patents.urls")),
]

admin.site.site_header = "Patent Portal Administration"
admin.site.site_title = "Patent Portal Admin"
admin.site.index_title = "Manage organizations and users"
