from django.db import migrations

PLANS = [
    # code, name, price_cents, monthly_api_calls, seats, sort_order
    ("free", "Free", 0, 100, 1, 1),
    ("starter", "Starter", 1900, 5_000, 5, 2),
    ("pro", "Pro", 4900, 50_000, 25, 3),
]


def seed(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for code, name, price, calls, seats, order in PLANS:
        Plan.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "price_cents": price,
                "monthly_api_calls": calls,
                "seats": seats,
                "sort_order": order,
                "is_active": True,
            },
        )


def unseed(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    Plan.objects.filter(code__in=[plan[0] for plan in PLANS]).delete()


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
