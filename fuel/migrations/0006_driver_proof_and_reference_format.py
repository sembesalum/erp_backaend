# Generated manually for driver proof fields and SEL reference format.

from django.db import migrations, models


def migrate_reference_prefix(apps, schema_editor):
    FuelRequest = apps.get_model("fuel", "FuelRequest")
    for row in FuelRequest.objects.all().only("id", "reference"):
        if not row.reference:
            row.reference = f"SEL-{row.id:04d}"
            row.save(update_fields=["reference"])
            continue
        if row.reference.startswith("FR-"):
            row.reference = f"SEL-{row.id:04d}"
            row.save(update_fields=["reference"])


class Migration(migrations.Migration):
    dependencies = [
        ("fuel", "0005_remove_driver_photo_base64"),
    ]

    operations = [
        migrations.AddField(
            model_name="fuelrequest",
            name="driver_pump_photo_base64",
            field=models.TextField(
                blank=True,
                help_text="Optional driver-submitted pump photo at approval completion stage.",
            ),
        ),
        migrations.AddField(
            model_name="fuelrequest",
            name="fuel_level_photo_base64",
            field=models.TextField(
                blank=True,
                help_text="Driver-submitted fuel level photo when creating MVFO (dashboard fuel gauge).",
            ),
        ),
        migrations.AddField(
            model_name="fuelrequest",
            name="odometer_photo_base64",
            field=models.TextField(
                blank=True,
                help_text="Driver-submitted odometer photo at approval completion stage.",
            ),
        ),
        migrations.RunPython(migrate_reference_prefix, migrations.RunPython.noop),
    ]
