from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import EmailLoginCode, ExternalIdentity, Organization, PortalUser, SeatPurchase, SubscriptionPlan, UserSubscription


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "access_type", "subscription_type", "is_active", "starts_at", "ends_at")
    list_filter = ("access_type", "is_active", "subscription_type")
    search_fields = ("name", "contact_person", "address")
    readonly_fields = ("created_at", "updated_at")


@admin.register(PortalUser)
class PortalUserAdmin(UserAdmin):
    model = PortalUser
    list_display = ("username", "email", "organization", "role", "is_portal_admin", "trial_ends_at", "is_active", "is_staff")
    list_filter = ("organization", "role", "is_portal_admin", "is_active", "is_staff")
    search_fields = ("username", "email", "organization__name")
    fieldsets = UserAdmin.fieldsets + (
        ("Client organization", {"fields": ("organization", "role")}),
        ("Portal administration", {"fields": ("is_portal_admin",)}),
        ("Individual trial", {"fields": ("trial_started_at", "trial_ends_at")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Contact and organization", {"fields": ("email", "organization", "role", "is_portal_admin")}),
    )
    readonly_fields = ("trial_started_at", "trial_ends_at")


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "billing_interval", "price_per_seat", "discount_percent", "discounted_price", "is_active")
    list_filter = ("billing_interval", "is_active")
    search_fields = ("name", "description")


@admin.register(SeatPurchase)
class SeatPurchaseAdmin(admin.ModelAdmin):
    list_display = ("organization", "plan", "seat_count", "starts_at", "ends_at", "total_price", "status", "payment_mode")
    list_filter = ("status", "plan", "starts_at", "ends_at")
    search_fields = ("organization__name", "created_by__email")
    readonly_fields = tuple(field.name for field in SeatPurchase._meta.fields)


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "purchase", "starts_at", "ends_at")
    list_filter = ("starts_at", "ends_at")
    search_fields = ("user__username", "user__email", "organization__name")
    readonly_fields = tuple(field.name for field in UserSubscription._meta.fields)


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
