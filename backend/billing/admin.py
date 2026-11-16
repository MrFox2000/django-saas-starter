from django.contrib import admin

from .models import Plan, Subscription, UsageRecord


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "price_cents",
        "price_display",
        "monthly_api_calls",
        "seats",
        "is_active",
    )
    list_editable = ("price_cents", "monthly_api_calls", "seats", "is_active")
    prepopulated_fields = {"code": ("name",)}


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("organization", "plan", "status", "current_period_end", "external_id")
    list_filter = ("status", "plan")
    search_fields = ("organization__name", "external_id")


@admin.register(UsageRecord)
class UsageRecordAdmin(admin.ModelAdmin):
    list_display = ("organization", "period", "api_calls")
    list_filter = ("period",)
    search_fields = ("organization__name",)
