"""Serializers for sign-up and JWT issuance."""

from __future__ import annotations

from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from orgs.models import Membership, Organization

from .models import User


class UserSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ("id", "email", "full_name", "display_name", "date_joined")
        read_only_fields = ("id", "date_joined")


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    organization_name = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ("email", "full_name", "password", "organization_name")

    def validate_email(self, value: str) -> str:
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    @transaction.atomic
    def create(self, validated_data):
        organization_name = validated_data.pop("organization_name", "") or ""
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)

        name = organization_name.strip() or f"{user.display_name}'s workspace"
        organization = Organization.objects.create(name=name)
        Membership.objects.create(
            organization=organization, user=user, role=Membership.Role.OWNER
        )
        return user


class TokenWithOrgSerializer(TokenObtainPairSerializer):
    """Puts the user's active organisation inside the access token."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        membership = (
            Membership.objects.filter(user=user)
            .select_related("organization")
            .order_by("created_at")
            .first()
        )
        if membership is not None:
            token["org_id"] = membership.organization_id
            token["org_slug"] = membership.organization.slug
            token["role"] = membership.role
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        membership = (
            Membership.objects.filter(user=self.user)
            .select_related("organization")
            .order_by("created_at")
            .first()
        )
        data["user"] = UserSerializer(self.user).data
        data["org"] = (
            {
                "id": membership.organization_id,
                "name": membership.organization.name,
                "slug": membership.organization.slug,
                "role": membership.role,
            }
            if membership
            else None
        )
        return data
