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
        return value.strip().upper()


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
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "reference", "created_at", "updated_at")


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
