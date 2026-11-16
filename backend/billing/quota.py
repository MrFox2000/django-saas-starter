"""Quota accounting.

One place decides whether an organisation may do metered work, so the rule
cannot drift between endpoints.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.db import transaction
from django.db.models import F

from .models import Plan, Subscription, UsageRecord


class QuotaExceeded(Exception):
    def __init__(self, used: int, limit: int, plan: Plan) -> None:
        super().__init__(f"Monthly limit of {limit} calls reached on the {plan.name} plan.")
        self.used = used
        self.limit = limit
        self.plan = plan


@dataclass(frozen=True)
class QuotaState:
    used: int
    limit: int
    remaining: int
    plan_code: str
    period: str


def current_period(today: date | None = None) -> date:
    today = today or date.today()
    return today.replace(day=1)


def get_plan(organization) -> Plan:
    subscription = Subscription.objects.select_related("plan").filter(
        organization=organization
    ).first()
    if subscription is not None:
        return subscription.plan
    return Plan.objects.filter(code="free").first() or Plan.objects.create(
        code="free", name="Free", price_cents=0, monthly_api_calls=100, seats=1
    )


def usage_for(organization, period: date | None = None) -> int:
    period = period or current_period()
    record = UsageRecord.objects.filter(organization=organization, period=period).first()
    return record.api_calls if record else 0


def quota_state(organization) -> QuotaState:
    plan = get_plan(organization)
    period = current_period()
    used = usage_for(organization, period)
    limit = plan.monthly_api_calls
    return QuotaState(
        used=used,
        limit=limit,
        remaining=max(limit - used, 0),
        plan_code=plan.code,
        period=period.isoformat(),
    )


@transaction.atomic
def consume(organization, amount: int = 1) -> QuotaState:
    """Record `amount` metered calls, or raise if that would exceed the plan."""
    plan = get_plan(organization)
    period = current_period()

    record, _ = UsageRecord.objects.select_for_update().get_or_create(
        organization=organization, period=period
    )
    if record.api_calls + amount > plan.monthly_api_calls:
        raise QuotaExceeded(used=record.api_calls, limit=plan.monthly_api_calls, plan=plan)

    UsageRecord.objects.filter(pk=record.pk).update(api_calls=F("api_calls") + amount)
    record.refresh_from_db()

    return QuotaState(
        used=record.api_calls,
        limit=plan.monthly_api_calls,
        remaining=max(plan.monthly_api_calls - record.api_calls, 0),
        plan_code=plan.code,
        period=period.isoformat(),
    )
