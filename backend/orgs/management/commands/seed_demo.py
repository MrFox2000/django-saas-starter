"""Create a demo organisation with members, a paid plan and some usage.

    python manage.py seed_demo

Idempotent: running it twice does not duplicate anything.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from billing import quota
from billing.models import Plan, Subscription
from orgs.models import Membership, Organization

DEMO_PASSWORD = "demo-pass-1234"

PEOPLE = [
    ("demo@example.com", "Demo Owner", Membership.Role.OWNER),
    ("admin@example.com", "Ada Admin", Membership.Role.ADMIN),
    ("member@example.com", "Mo Member", Membership.Role.MEMBER),
    ("second@example.com", "Sam Second", Membership.Role.MEMBER),
]


class Command(BaseCommand):
    help = "Seed a demo organisation, users, subscription and usage."

    def add_arguments(self, parser):
        parser.add_argument("--calls", type=int, default=342, help="Metered calls to record")

    @transaction.atomic
    def handle(self, *args, **options):
        plan = Plan.objects.filter(code="starter").first() or Plan.objects.create(
            code="starter", name="Starter", price_cents=1900, monthly_api_calls=5000, seats=5
        )

        organization, _ = Organization.objects.get_or_create(
            slug="acme-labs", defaults={"name": "Acme Labs"}
        )

        for email, full_name, role in PEOPLE:
            user, created = User.objects.get_or_create(
                email=email, defaults={"full_name": full_name}
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=["password"])
            Membership.objects.get_or_create(
                organization=organization, user=user, defaults={"role": role}
            )

        Subscription.objects.update_or_create(
            organization=organization,
            defaults={
                "plan": plan,
                "status": Subscription.Status.ACTIVE,
                "current_period_end": timezone.now() + timedelta(days=30),
                "external_id": "fake_seeded",
            },
        )

        record = quota.UsageRecord.objects.filter(
            organization=organization, period=quota.current_period()
        ).first()
        if record is None:
            quota.UsageRecord.objects.create(
                organization=organization,
                period=quota.current_period(),
                api_calls=max(options["calls"], 0),
            )

        self.stdout.write(self.style.SUCCESS("Seeded Acme Labs"))
        self.stdout.write(f"  login: demo@example.com / {DEMO_PASSWORD}")
        self.stdout.write(f"  plan : {plan.name} ({plan.monthly_api_calls} calls/month)")
