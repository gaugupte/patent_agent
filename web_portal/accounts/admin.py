from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import EmailLoginCode, ExternalIdentity, Organization, PortalUser


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


@admin.register(ExternalIdentity)
class ExternalIdentityAdmin(admin.ModelAdmin):
    list_display = ("user", "issuer", "email", "created_at")
    search_fields = ("user__username", "email", "subject")
    readonly_fields = ("user", "issuer", "subject", "email", "created_at")


@admin.register(EmailLoginCode)
class EmailLoginCodeAdmin(admin.ModelAdmin):
    list_display = ("email", "created_at", "expires_at", "attempts", "consumed_at")
    search_fields = ("email",)
    readonly_fields = tuple(field.name for field in EmailLoginCode._meta.fields)
