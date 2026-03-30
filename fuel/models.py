from django.conf import settings
from django.db import models


class FuelStation(models.Model):
    name = models.CharField(max_length=255)
    region = models.CharField(max_length=128)
    address = models.CharField(max_length=512, blank=True)
    contact_phone = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Driver(models.Model):
    """Driver profile; links to a user account with role DRIVER."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="driver_profile",
    )
    assigned_station = models.ForeignKey(
        FuelStation,
        on_delete=models.PROTECT,
        related_name="drivers",
    )
    license_number = models.CharField(max_length=64)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user.full_name} ({self.license_number})"


class Vehicle(models.Model):
    class FuelType(models.TextChoices):
        DIESEL = "Diesel", "Diesel"
        PETROL = "Petrol", "Petrol"
        KEROSENE = "Kerosene", "Kerosene"

    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name="vehicles")
    plate = models.CharField(max_length=32, unique=True, db_index=True)
    make = models.CharField(max_length=64)
    model = models.CharField(max_length=64)
    year = models.PositiveSmallIntegerField()
    default_fuel_type = models.CharField(max_length=16, choices=FuelType.choices)
    is_active = models.BooleanField(default=True)
    registered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-registered_at"]

    def __str__(self) -> str:
        return self.plate


class FuelPrice(models.Model):
    class FuelType(models.TextChoices):
        DIESEL = "Diesel", "Diesel"
        PETROL = "Petrol", "Petrol"
        KEROSENE = "Kerosene", "Kerosene"

    station = models.ForeignKey(FuelStation, on_delete=models.CASCADE, related_name="fuel_prices")
    fuel_type = models.CharField(max_length=16, choices=FuelType.choices)
    price_per_litre = models.DecimalField(max_digits=12, decimal_places=2)
    effective_from = models.DateTimeField()
    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fuel_prices_set",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_from"]
        indexes = [
            models.Index(fields=["station", "fuel_type", "-effective_from"]),
        ]

    def __str__(self) -> str:
        return f"{self.station.name} {self.fuel_type} @ {self.price_per_litre}"


class FuelRequest(models.Model):
    """Motor Vehicle Fuel Order (MVFO)."""

    class LegacyStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        FUEL_ISSUED = "FUEL_ISSUED", "Fuel issued"
        COMPLETED = "COMPLETED", "Completed"
        REJECTED = "REJECTED", "Rejected"

    class MvfoStatus(models.TextChoices):
        CREATED = "CREATED", "Created"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        ACCEPTED = "ACCEPTED", "Accepted"
        COLLECTION = "COLLECTION", "Collection"
        COMPLETED = "COMPLETED", "Completed"
        PARTIAL = "PARTIAL", "Partial"
        INCOMPLETE = "INCOMPLETE", "Incomplete"
        COLLECTED = "COLLECTED", "Collected"

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        DRIVER = "DRIVER", "Driver"
        APPROVER = "APPROVER", "Approver"
        SIMBA_OIL = "SIMBA_OIL", "Simba Oil"
        QSE = "QSE", "QSE"

    class FuelType(models.TextChoices):
        DIESEL = "Diesel", "Diesel"
        PETROL = "Petrol", "Petrol"
        KEROSENE = "Kerosene", "Kerosene"

    reference = models.CharField(max_length=32, unique=True, null=True, blank=True, editable=False)
    driver = models.ForeignKey(Driver, on_delete=models.PROTECT, related_name="fuel_requests")
    station = models.ForeignKey(FuelStation, on_delete=models.PROTECT, related_name="fuel_requests")
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fuel_requests",
    )
    fuel_type = models.CharField(max_length=16, choices=FuelType.choices)
    quantity_is_money = models.BooleanField(default=False)
    quantity_value = models.DecimalField(max_digits=14, decimal_places=2)
    litres_requested = models.DecimalField(max_digits=12, decimal_places=2)
    approved_litres = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    issued_litres = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    attendant_name = models.CharField(max_length=128, blank=True)
    request_datetime = models.DateTimeField()
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=LegacyStatus.choices, default=LegacyStatus.PENDING)
    mvfo_status = models.CharField(max_length=20, choices=MvfoStatus.choices, default=MvfoStatus.CREATED)
    owner_role = models.CharField(max_length=20, choices=Role.choices)
    price_per_litre = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    partial_reason = models.TextField(blank=True)
    incomplete_reason = models.TextField(blank=True)
    has_pump_meter_photo = models.BooleanField(default=False)
    has_gps_capture = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-request_datetime"]

    def save(self, *args, **kwargs):
        adding = self._state.adding
        super().save(*args, **kwargs)
        if adding and not self.reference:
            self.reference = f"FR-{self.pk:05d}"
            super().save(update_fields=["reference"])

    def __str__(self) -> str:
        return self.reference or f"#{self.pk}"


class RequestTimelineEvent(models.Model):
    fuel_request = models.ForeignKey(FuelRequest, on_delete=models.CASCADE, related_name="timeline_events")
    action = models.CharField(max_length=255)
    actor_name = models.CharField(max_length=255)
    actor_role = models.CharField(max_length=20, choices=FuelRequest.Role.choices)
    at = models.DateTimeField()
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ["at"]


class AuditLog(models.Model):
    action = models.CharField(max_length=128, db_index=True)
    actor_name = models.CharField(max_length=255)
    role = models.CharField(max_length=20, choices=FuelRequest.Role.choices)
    target = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp"]


class OperationActivity(models.Model):
    class Category(models.TextChoices):
        MASTER_DATA = "master_data", "Master data"
        MVFO = "mvfo", "MVFO"
        SECURITY = "security", "Security"
        ASSIGNMENT = "assignment", "Assignment"

    category = models.CharField(max_length=32, choices=Category.choices)
    summary = models.CharField(max_length=512)
    actor_name = models.CharField(max_length=255)
    role = models.CharField(max_length=20, choices=FuelRequest.Role.choices)
    related_entity = models.CharField(max_length=255)
    timestamp = models.DateTimeField()
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name_plural = "Operation activities"
