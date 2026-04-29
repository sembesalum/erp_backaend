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
    """Create via API. Driver email may be omitted — set in validate() to a synthetic address."""

    password = serializers.CharField(write_only=True)
    email = serializers.EmailField(required=False, allow_blank=True)
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
        phone = (attrs.get("phone") or "").strip()
        attrs["phone"] = phone
        region = (attrs.get("region") or "").strip()
        if "region" in attrs:
            attrs["region"] = region
        station = attrs.get("assigned_station")

        if len(phone) < 6:
            raise serializers.ValidationError({"phone": "Phone is required and must be valid."})
        if User.objects.filter(phone=phone).exists():
            raise serializers.ValidationError({"phone": "This phone number is already in use."})

        email = (attrs.get("email") or "").strip().lower()
        if not email:
            email = f"user_{uuid.uuid4().hex[:20]}@users.internal"
        attrs["email"] = email
        attrs["username"] = attrs["email"]

        if role == User.Role.DRIVER:
            if len(pwd) < 4:
                raise serializers.ValidationError(
                    {"password": "Use at least 4 characters for driver accounts."}
                )
        else:
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
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
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
        phone = attrs["phone"] if "phone" in attrs else inst.phone
        phone = (phone or "").strip()
        if not phone or len(phone) < 6:
            raise serializers.ValidationError({"phone": "Phone is required and must be valid."})
        if User.objects.filter(phone=phone).exclude(pk=inst.pk).exists():
            raise serializers.ValidationError({"phone": "This phone number is already in use."})
        attrs["phone"] = phone

        if "email" in attrs:
            email = (attrs.get("email") or "").strip().lower()
            attrs["email"] = email if email else inst.email

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
        next_email = validated_data.get("email", instance.email)
        validated_data["username"] = next_email
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        return user
