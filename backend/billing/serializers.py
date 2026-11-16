from __future__ import annotations

from rest_framework import serializers

from .models import Plan, Subscription, UsageRecord


class PlanSerializer(serializers.ModelSerializer):
    price_display = serializers.CharField(read_only=True)

    class Meta:
        model = Plan
        fields = (
            "id",
            "code",
            "name",
            "price_cents",
            "price_display",
            "currency",
            "monthly_api_calls",
            "seats",
        )


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    is_current = serializers.BooleanField(read_only=True)

    class Meta:
        model = Subscription
        fields = ("id", "plan", "status", "is_current", "current_period_end", "created_at")


class UsageRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = UsageRecord
        fields = ("period", "api_calls")


class CheckoutSerializer(serializers.Serializer):
    plan_code = serializers.SlugField()
