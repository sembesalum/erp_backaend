from django.contrib import admin

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


@admin.register(FuelStation)
class FuelStationAdmin(admin.ModelAdmin):
    list_display = ("name", "region", "is_active", "contact_phone")
    list_filter = ("is_active", "region")
    search_fields = ("name", "region")


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ("user", "assigned_station", "license_number", "is_active")
    list_filter = ("is_active", "assigned_station")
    search_fields = ("user__email", "user__full_name", "license_number")


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("plate", "driver", "make", "model", "year", "is_active")
    list_filter = ("is_active", "default_fuel_type")
    search_fields = ("plate", "make", "model")


@admin.register(FuelPrice)
class FuelPriceAdmin(admin.ModelAdmin):
    list_display = ("station", "fuel_type", "price_per_litre", "effective_from")
    list_filter = ("fuel_type",)


@admin.register(FuelRequest)
class FuelRequestAdmin(admin.ModelAdmin):
    list_display = ("reference", "driver", "station", "mvfo_status", "status", "request_datetime")
    list_filter = ("mvfo_status", "status", "fuel_type")
    search_fields = ("reference", "notes")


@admin.register(RequestTimelineEvent)
class RequestTimelineEventAdmin(admin.ModelAdmin):
    list_display = ("fuel_request", "action", "actor_name", "at")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "actor_name", "target", "timestamp")


@admin.register(OperationActivity)
class OperationActivityAdmin(admin.ModelAdmin):
    list_display = ("summary", "category", "actor_name", "timestamp")
