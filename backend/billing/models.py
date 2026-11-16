"""Plans, subscriptions and metered usage."""

from __future__ import annotations

from django.db import models
from django.utils import timezone

from orgs.models import Organization


class Plan(models.Model):
    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    price_cents = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default="usd")
    monthly_api_calls = models.PositiveIntegerField(default=1000)
    seats = models.PositiveSmallIntegerField(default=3)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "price_cents"]

    def __str__(self) -> str:
        return f"{self.name} (${self.price_cents / 100:.0f})"

    @property
    def price_display(self) -> str:
        return f"${self.price_cents / 100:.0f}" if self.price_cents else "Free"


class Subscription(models.Model):
    class Status(models.TextChoices):
        TRIALING = "trialing", "Trialing"
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past due"
        CANCELED = "canceled", "Canceled"

    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name="subscription"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.TRIALING)
    current_period_end = models.DateTimeField(null=True, blank=True)
    external_id = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.organization} -> {self.plan.code} ({self.status})"

    @property
    def is_current(self) -> bool:
        if self.status == self.Status.ACTIVE:
            return True
        if self.status == self.Status.TRIALING:
            return self.current_period_end is None or self.current_period_end > timezone.now()
        return False


class UsageRecord(models.Model):
    """One row per organisation per calendar month."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="usage"
    )
    period = models.DateField(help_text="First day of the month this row covers")
    api_calls = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-period"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "period"], name="unique_usage_per_period"
            )
        ]

    def __str__(self) -> str:
        return f"{self.organization} {self.period:%Y-%m}: {self.api_calls}"
