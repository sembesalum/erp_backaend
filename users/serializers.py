import uuid

from rest_framework import serializers

from fuel.models import FuelStation

from .models import User


class UserSerializer(serializers.ModelSerializer):
    assigned_station = serializers.SerializerMethodField()
    assigned_station_id = serializers.PrimaryKeyRelatedField(
        queryset=FuelStation.objects.all(),
        source="assigned_station",
        required=False,
        allow_null=True,
        write_only=True,
    )

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "full_name",
            "role",
            "phone",
            "region",
            "assigned_station",
            "assigned_station_id",
            "is_active",
            "date_joined",
        )
        read_only_fields = ("id", "date_joined")

    def get_assigned_station(self, obj: User):
        if obj.assigned_station_id is None:
            return None
        s = obj.assigned_station
        return {"id": s.pk, "name": s.name, "region": s.region}


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    assigned_station_id = serializers.PrimaryKeyRelatedField(
        queryset=FuelStation.objects.all(),
        source="assigned_station",
        required=False,
        allow_null=True,
    )

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "full_name",
            "role",
            "phone",
            "region",
            "assigned_station_id",
            "password",
            "is_active",
        )
        read_only_fields = ("id",)

    def validate(self, attrs: dict) -> dict:
        role = attrs.get("role")
        pwd = attrs.get("password") or ""
        region = (attrs.get("region") or "").strip()
        if "region" in attrs:
            attrs["region"] = region
        station = attrs.get("assigned_station")

        if role == User.Role.DRIVER:
            email = (attrs.get("email") or "").strip()
            if not email:
                attrs["email"] = f"driver_{uuid.uuid4().hex[:20]}@drivers.internal"
            else:
                attrs["email"] = email.lower()
            attrs["username"] = attrs["email"]
            if len(pwd) < 4:
                raise serializers.ValidationError(
                    {"password": "Use at least 4 characters for driver accounts."}
                )
        else:
            if not (attrs.get("email") or "").strip():
                raise serializers.ValidationError({"email": "Email is required."})
            attrs["email"] = (attrs["email"] or "").strip().lower()
            attrs.setdefault("username", attrs["email"])
            if len(pwd) < 8:
                raise serializers.ValidationError(
                    {"password": "Use at least 8 characters."}
                )

        if role == User.Role.SIMBA_OIL:
            if station is None:
                raise serializers.ValidationError(
                    {"assigned_station_id": "Assign a fuel station for Simba Oil (station admin) accounts."}
                )
            attrs.setdefault("region", station.region)

        if role == User.Role.APPROVER:
            if not region:
                raise serializers.ValidationError(
                    {"region": "Set a coverage region or area label for this approver (e.g. Dar es Salaam)."}
                )

        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        validated_data.setdefault("username", validated_data["email"])
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    """Admin updates; optional password change."""

    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    assigned_station_id = serializers.PrimaryKeyRelatedField(
        queryset=FuelStation.objects.all(),
        source="assigned_station",
        required=False,
        allow_null=True,
    )

    class Meta:
        model = User
        fields = (
            "email",
            "full_name",
            "role",
            "phone",
            "region",
            "assigned_station_id",
            "is_active",
            "password",
        )

    def validate(self, attrs: dict) -> dict:
        inst = self.instance
        role = attrs.get("role", inst.role)
        region = attrs["region"] if "region" in attrs else inst.region
        region = (region or "").strip()
        if "region" in attrs:
            attrs["region"] = region
        station = attrs.get("assigned_station") if "assigned_station_id" in attrs else inst.assigned_station

        if role == User.Role.SIMBA_OIL:
            if station is None:
                raise serializers.ValidationError(
                    {"assigned_station_id": "Assign a fuel station for Simba Oil accounts."}
                )
            if "region" not in attrs or not (attrs.get("region") or "").strip():
                attrs["region"] = station.region
        if role == User.Role.APPROVER:
            reg = (attrs["region"] if "region" in attrs else inst.region) or ""
            if not reg.strip():
                raise serializers.ValidationError(
                    {"region": "Set a coverage region for approvers."}
                )

        pwd = attrs.get("password")
        if pwd is not None and pwd != "" and len(pwd) < 8:
            raise serializers.ValidationError({"password": "Minimum 8 characters."})

        return attrs

    def update(self, instance: User, validated_data: dict) -> User:
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        return user
