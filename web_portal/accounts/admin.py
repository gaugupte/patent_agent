from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Organization, PortalUser


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "subscription_type", "is_active", "starts_at", "ends_at")
    list_filter = ("is_active", "subscription_type")
    search_fields = ("name", "contact_person", "address")
    readonly_fields = ("created_at", "updated_at")


@admin.register(PortalUser)
class PortalUserAdmin(UserAdmin):
    model = PortalUser
    list_display = ("username", "email", "organization", "is_active", "is_staff")
    list_filter = ("organization", "is_active", "is_staff")
    search_fields = ("username", "email", "organization__name")
    fieldsets = UserAdmin.fieldsets + (("Client organization", {"fields": ("organization",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Contact and organization", {"fields": ("email", "organization")}),
    )
