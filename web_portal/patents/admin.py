from django.contrib import admin

from .models import Customer, Invention, InventionVersion


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "created_at")
    list_filter = ("organization",)
    search_fields = ("name", "organization__name")
    readonly_fields = ("created_at", "updated_at")


class InventionVersionInline(admin.TabularInline):
    model = InventionVersion
    extra = 0
    readonly_fields = ("number", "status", "created_at", "completed_at", "report_path")
    fields = ("number", "status", "created_at", "completed_at", "report_path")
    can_delete = False


@admin.register(Invention)
class InventionAdmin(admin.ModelAdmin):
    list_display = ("invention_number", "title", "customer", "created_at")
    list_filter = ("customer__organization",)
    search_fields = ("title", "customer__name")
    readonly_fields = ("created_at", "updated_at")
    inlines = (InventionVersionInline,)


@admin.register(InventionVersion)
class InventionVersionAdmin(admin.ModelAdmin):
    list_display = ("invention", "number", "status", "created_at", "completed_at")
    list_filter = ("status", "invention__customer__organization")
    search_fields = ("invention__title", "invention__customer__name")
    readonly_fields = ("created_at", "completed_at", "analysis_result", "report_path")
