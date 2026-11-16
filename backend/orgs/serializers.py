"""Serializers for organisations, members and the metered report endpoint."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Membership, Organization

User = get_user_model()


class OrganizationSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = ("id", "name", "slug", "created_at", "role")
        read_only_fields = ("id", "slug", "created_at")

    def get_role(self, obj) -> str | None:
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return None
        membership = Membership.objects.filter(organization=obj, user=request.user).first()
        return membership.role if membership else None


class MemberSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = Membership
        fields = ("id", "email", "full_name", "role", "created_at")
        read_only_fields = ("id", "created_at")


class MemberCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=Membership.Role.choices, default=Membership.Role.MEMBER
    )

    def validate(self, attrs):
        organization: Organization = self.context["organization"]
        user = User.objects.filter(email__iexact=attrs["email"]).first()
        if user is None:
            raise serializers.ValidationError(
                {"email": "No account with that email. Ask them to sign up first."}
            )
        if Membership.objects.filter(organization=organization, user=user).exists():
            raise serializers.ValidationError({"email": "That person is already a member."})

        seats = organization.subscription.plan.seats if hasattr(organization, "subscription") else 1
        if organization.memberships.count() >= seats:
            raise serializers.ValidationError(
                {"detail": f"This plan allows {seats} seat(s). Upgrade to invite more people."}
            )

        attrs["user"] = user
        return attrs


class MemberRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Membership.Role.choices)
