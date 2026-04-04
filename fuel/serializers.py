from decimal import Decimal

from rest_framework import serializers

from users.models import User
from users.serializers import UserSerializer

from .models import (
    AuditLog,
    Driver,
    FuelPrice,
    FuelRequest,
    FuelStation,
    OperationActivity,
    RequestTimelineEvent,
    Vehicle,
)


class FuelStationSerializer(serializers.ModelSerializer):
    class Meta:
        model = FuelStation
        fields = (
            "id",
            "name",
            "region",
            "address",
            "contact_phone",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class VehicleSerializer(serializers.ModelSerializer):
    driver_id = serializers.PrimaryKeyRelatedField(queryset=Driver.objects.all(), source="driver")

    class Meta:
        model = Vehicle
        fields = (
            "id",
            "driver_id",
            "plate",
            "make",
            "model",
            "year",
            "default_fuel_type",
            "is_active",
            "registered_at",
            "updated_at",
        )
        read_only_fields = ("id", "registered_at", "updated_at")

    def validate_plate(self, value: str) -> str:
        plate = value.strip().upper()
        qs = Vehicle.objects.filter(plate=plate)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "This plate is already registered on another vehicle.",
            )
        return plate


class DriverSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    vehicles = VehicleSerializer(many=True, read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=User.Role.DRIVER),
        source="user",
        write_only=True,
    )
    assigned_station = FuelStationSerializer(read_only=True)
    assigned_station_id = serializers.PrimaryKeyRelatedField(
        queryset=FuelStation.objects.all(),
        source="assigned_station",
        write_only=True,
    )

    class Meta:
        model = Driver
        fields = (
            "id",
            "user",
            "vehicles",
            "user_id",
            "assigned_station",
            "assigned_station_id",
            "license_number",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class FuelPriceSerializer(serializers.ModelSerializer):
    station = FuelStationSerializer(read_only=True)
    station_id = serializers.PrimaryKeyRelatedField(
        queryset=FuelStation.objects.all(),
        source="station",
        write_only=True,
    )
    set_by_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source="set_by",
        required=False,
        allow_null=True,
    )

    class Meta:
        model = FuelPrice
        fields = (
            "id",
            "station",
            "station_id",
            "fuel_type",
            "price_per_litre",
            "effective_from",
            "set_by",
            "set_by_id",
            "created_at",
        )
        read_only_fields = ("id", "station", "set_by", "created_at")


class FuelRequestSerializer(serializers.ModelSerializer):
    driver_id = serializers.PrimaryKeyRelatedField(queryset=Driver.objects.all(), source="driver")
    station_id = serializers.PrimaryKeyRelatedField(queryset=FuelStation.objects.all(), source="station")
    vehicle_id = serializers.PrimaryKeyRelatedField(
        queryset=Vehicle.objects.all(),
        source="vehicle",
        required=False,
        allow_null=True,
    )
    driver_name = serializers.CharField(source="driver.user.full_name", read_only=True)
    station_name = serializers.CharField(source="station.name", read_only=True)
    vehicle = VehicleSerializer(read_only=True)
    vehicle_plate = serializers.SerializerMethodField()
    has_driver_photo = serializers.SerializerMethodField()
    has_efd_receipt = serializers.SerializerMethodField()

    def get_has_driver_photo(self, obj: FuelRequest) -> bool:
        return bool((obj.driver_photo_base64 or "").strip())

    def get_has_efd_receipt(self, obj: FuelRequest) -> bool:
        return bool((obj.efd_receipt_base64 or "").strip())

    def get_vehicle_plate(self, obj: FuelRequest) -> str:
        """Plate from MVFO vehicle FK, else first active vehicle on the driver (legacy rows)."""
        rel = getattr(obj, "vehicle", None)
        if rel is not None:
            plate = (rel.plate or "").strip()
            if plate:
                return plate
        v = (
            obj.driver.vehicles.filter(is_active=True)
            .order_by("-registered_at")
            .first()
        )
        if v is None or not v.plate:
            return ""
        return v.plate.strip()

    class Meta:
        model = FuelRequest
        fields = (
            "id",
            "reference",
            "driver_id",
            "station_id",
            "vehicle_id",
            "vehicle",
            "driver_name",
            "station_name",
            "vehicle_plate",
            "fuel_type",
            "full_tank",
            "quantity_is_money",
            "quantity_value",
            "litres_requested",
            "approved_litres",
            "issued_litres",
            "attendant_name",
            "request_datetime",
            "notes",
            "status",
            "mvfo_status",
            "owner_role",
            "price_per_litre",
            "rejection_reason",
            "partial_reason",
            "incomplete_reason",
            "has_pump_meter_photo",
            "has_gps_capture",
            "gps_capture_text",
            "pump_meter_photo_base64",
            "driver_photo_base64",
            "efd_receipt_base64",
            "has_driver_photo",
            "has_efd_receipt",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "reference",
            "created_at",
            "updated_at",
            "has_driver_photo",
            "has_efd_receipt",
        )

    def validate(self, attrs):
        full_tank = attrs.get("full_tank")
        if self.instance is not None and full_tank is None:
            full_tank = self.instance.full_tank
        if full_tank is None:
            full_tank = False

        if full_tank:
            attrs["full_tank"] = True
            attrs["quantity_value"] = Decimal("0")
            attrs["litres_requested"] = Decimal("0")
            attrs["quantity_is_money"] = False

        owner_role = attrs.get("owner_role")
        if owner_role is None and self.instance is not None:
            owner_role = self.instance.owner_role

        is_create = self.instance is None
        if is_create and owner_role == FuelRequest.Role.DRIVER:
            dp = (attrs.get("driver_photo_base64") or "").strip()
            efd = (attrs.get("efd_receipt_base64") or "").strip()
            if not dp:
                raise serializers.ValidationError(
                    {"driver_photo_base64": "Driver photo proof is required."},
                )
            if not efd:
                raise serializers.ValidationError(
                    {"efd_receipt_base64": "EFD receipt evidence is required."},
                )

        if is_create and not full_tank:
            qv = attrs.get("quantity_value")
            if qv is None:
                raise serializers.ValidationError(
                    {"quantity_value": "Enter a quantity or choose full tank."},
                )
            try:
                qv_dec = qv if isinstance(qv, Decimal) else Decimal(str(qv))
            except Exception:
                raise serializers.ValidationError(
                    {"quantity_value": "Invalid quantity."},
                ) from None
            if qv_dec <= 0:
                raise serializers.ValidationError(
                    {
                        "quantity_value": (
                            "Quantity must be greater than zero unless full tank is selected."
                        ),
                    },
                )

        return attrs


class FuelRequestUpdateSerializer(serializers.ModelSerializer):
    """Partial updates for approvers and station staff (not for creating rows)."""

    class Meta:
        model = FuelRequest
        fields = (
            "mvfo_status",
            "status",
            "approved_litres",
            "issued_litres",
            "rejection_reason",
            "partial_reason",
            "incomplete_reason",
            "price_per_litre",
            "attendant_name",
            "has_pump_meter_photo",
            "has_gps_capture",
            "gps_capture_text",
            "pump_meter_photo_base64",
            "notes",
        )


class FuelRequestDetailSerializer(FuelRequestSerializer):
    driver = DriverSerializer(read_only=True)
    station = FuelStationSerializer(read_only=True)

    class Meta(FuelRequestSerializer.Meta):
        fields = tuple(FuelRequestSerializer.Meta.fields) + ("driver", "station")


class RequestTimelineEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = RequestTimelineEvent
        fields = ("id", "fuel_request", "action", "actor_name", "actor_role", "at", "reason")
        read_only_fields = ("id",)


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ("id", "action", "actor_name", "role", "target", "timestamp", "metadata")
        read_only_fields = ("id", "timestamp")


class OperationActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = OperationActivity
        fields = (
            "id",
            "category",
            "summary",
            "actor_name",
            "role",
            "related_entity",
            "timestamp",
            "details",
        )
        read_only_fields = ("id",)
