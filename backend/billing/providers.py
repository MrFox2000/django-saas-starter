"""Billing providers.

`StripeProvider` is the real one. `FakeProvider` keeps the whole flow - checkout,
activation, cancellation - runnable locally and in tests without keys, which is
also what makes the demo honest: the UI you can click really does exercise the
subscription state machine.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from django.conf import settings
from datetime import timedelta

from django.utils import timezone

from .models import Plan, Subscription


class BillingError(Exception):
    pass


class BillingProvider(Protocol):
    name: str

    def start_checkout(self, organization, plan: Plan) -> str: ...

    def cancel(self, subscription: Subscription) -> None: ...


class FakeProvider:
    """Activates the subscription immediately and returns a local success URL."""

    name = "fake"

    def start_checkout(self, organization, plan: Plan) -> str:
        subscription, _ = Subscription.objects.get_or_create(
            organization=organization, defaults={"plan": plan}
        )
        subscription.plan = plan
        subscription.status = Subscription.Status.ACTIVE
        subscription.external_id = f"fake_{uuid.uuid4().hex[:16]}"
        subscription.current_period_end = timezone.now() + timedelta(days=30)
        subscription.save()
        return f"{settings.FRONTEND_URL}/billing/success?plan={plan.code}&provider=fake"

    def cancel(self, subscription: Subscription) -> None:
        subscription.status = Subscription.Status.CANCELED
        subscription.save(update_fields=["status", "updated_at"])


class StripeProvider:
    """Creates a real Stripe Checkout session.

    The session id is stored on the subscription; activation happens when Stripe
    calls the webhook, not before.
    """

    name = "stripe"

    def __init__(self) -> None:
        import stripe

        if not settings.STRIPE_SECRET_KEY:
            raise BillingError("STRIPE_SECRET_KEY is not configured")
        self._stripe = stripe
        self._stripe.api_key = settings.STRIPE_SECRET_KEY

    def start_checkout(self, organization, plan: Plan) -> str:
        if plan.price_cents <= 0:
            raise BillingError("Free plans do not need checkout")

        session = self._stripe.checkout.Session.create(
            mode="subscription",
            line_items=[
                {
                    "price_data": {
                        "currency": plan.currency,
                        "unit_amount": plan.price_cents,
                        "recurring": {"interval": "month"},
                        "product_data": {"name": plan.name},
                    },
                    "quantity": 1,
                }
            ],
            success_url=f"{settings.FRONTEND_URL}/billing/success?plan={plan.code}",
            cancel_url=f"{settings.FRONTEND_URL}/billing/cancel",
            client_reference_id=str(organization.pk),
            metadata={"organization_id": organization.pk, "plan_code": plan.code},
        )

        subscription, _ = Subscription.objects.get_or_create(
            organization=organization, defaults={"plan": plan}
        )
        subscription.plan = plan
        subscription.status = Subscription.Status.TRIALING
        subscription.external_id = session.id
        subscription.save()
        return session.url

    def cancel(self, subscription: Subscription) -> None:
        if subscription.external_id and not subscription.external_id.startswith("fake_"):
            self._stripe.Subscription.cancel(subscription.external_id)
        subscription.status = Subscription.Status.CANCELED
        subscription.save(update_fields=["status", "updated_at"])


def get_provider() -> BillingProvider:
    if settings.STRIPE_SECRET_KEY:
        return StripeProvider()
    return FakeProvider()
