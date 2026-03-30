from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        extra_fields.setdefault("username", email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "ADMIN")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Auth user shared by dashboard and mobile app."""

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        DRIVER = "DRIVER", "Driver"
        APPROVER = "APPROVER", "Approver"
        SIMBA_OIL = "SIMBA_OIL", "Simba Oil"
        QSE = "QSE", "QSE"

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255)
    role = models.CharField(max_length=20, choices=Role.choices)
    phone = models.CharField(max_length=32, blank=True)
    region = models.CharField(max_length=128, blank=True)
    assigned_station = models.ForeignKey(
        "fuel.FuelStation",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_staff",
        help_text="Simba Oil / station-facing staff; approvers may optionally be scoped to a station.",
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = ["full_name"]

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.email
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.full_name} <{self.email}>"
