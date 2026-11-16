"""Billing endpoints: plans, subscription, checkout, cancel, Stripe webhook."""

from __future__ import annotations

import json
import logging

from django.conf import settings
from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from orgs.permissions import HasOrganization, IsOrgAdmin, IsOrgOwner

from . import quota
from .models import Plan, Subscription
from .providers import BillingError, get_provider
from .serializers import CheckoutSerializer, PlanSerializer, SubscriptionSerializer

logger = logging.getLogger(__name__)


class PlanListView(APIView):
    """Public price list, so a landing page can render it before anyone signs up."""

    permission_classes = [AllowAny]

    def get(self, request):
        plans = Plan.objects.filter(is_active=True)
        return Response(PlanSerializer(plans, many=True).data)


class SubscriptionView(APIView):
    permission_classes = [HasOrganization]

    def get(self, request):
        subscription = Subscription.objects.select_related("plan").filter(
            organization=request.organization
        ).first()
        return Response(
            {
                "subscription": SubscriptionSerializer(subscription).data if subscription else None,
                "quota": vars(quota.quota_state(request.organization)),
                "provider": get_provider().name,
            }
        )


class CheckoutView(APIView):
    permission_classes = [IsOrgAdmin]

    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plan = Plan.objects.filter(code=serializer.validated_data["plan_code"], is_active=True).first()
        if plan is None:
            return Response({"detail": "Unknown plan."}, status=status.HTTP_404_NOT_FOUND)

        try:
            url = get_provider().start_checkout(request.organization, plan)
        except BillingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "checkout_url": url,
                "plan": PlanSerializer(plan).data,
                "provider": get_provider().name,
            }
        )


class CancelView(APIView):
    permission_classes = [IsOrgOwner]

    def post(self, request):
        subscription = Subscription.objects.filter(organization=request.organization).first()
        if subscription is None:
            return Response({"detail": "No subscription to cancel."}, status=status.HTTP_404_NOT_FOUND)

        get_provider().cancel(subscription)
        subscription.refresh_from_db()
        return Response(SubscriptionSerializer(subscription).data)


class StripeWebhookView(APIView):
    """Activates a subscription when Stripe confirms the checkout."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request):
        import stripe

        payload = request.body
        signature = request.headers.get("Stripe-Signature", "")

        try:
            if settings.STRIPE_WEBHOOK_SECRET:
                event = stripe.Webhook.construct_event(
                    payload, signature, settings.STRIPE_WEBHOOK_SECRET
                )
            else:
                event = json.loads(payload)
        except Exception as exc:  # bad signature, bad json
            logger.warning("Rejected Stripe webhook: %s", exc)
            return Response({"detail": "Invalid payload."}, status=status.HTTP_400_BAD_REQUEST)

        event = dict(event)
        if event.get("type") != "checkout.session.completed":
            return Response({"received": True})

        session = event["data"]["object"]
        organization_id = session.get("client_reference_id") or session.get("metadata", {}).get(
            "organization_id"
        )
        plan_code = session.get("metadata", {}).get("plan_code")

        subscription = Subscription.objects.filter(organization_id=organization_id).first()
        plan = Plan.objects.filter(code=plan_code).first() if plan_code else None
        if subscription and plan:
            subscription.plan = plan
            subscription.status = Subscription.Status.ACTIVE
            subscription.current_period_end = timezone.now() + timedelta(days=30)
            subscription.external_id = session.get("subscription") or ""
            subscription.save()

        return Response({"received": True})
