# Generated manually for kerosene removal and MVFO driver evidence fields.

from django.db import migrations, models


def migrate_kerosene_to_diesel(apps, schema_editor):
    Vehicle = apps.get_model("fuel", "Vehicle")
    Vehicle.objects.filter(default_fuel_type="Kerosene").update(default_fuel_type="Diesel")
    FuelPrice = apps.get_model("fuel", "FuelPrice")
    FuelPrice.objects.filter(fuel_type="Kerosene").update(fuel_type="Diesel")
    FuelRequest = apps.get_model("fuel", "FuelRequest")
    FuelRequest.objects.filter(fuel_type="Kerosene").update(fuel_type="Diesel")


class Migration(migrations.Migration):

    dependencies = [
        ("fuel", "0003_fuel_evidence_driver_email"),
    ]

    operations = [
        migrations.AddField(
            model_name="fuelrequest",
            name="full_tank",
            field=models.BooleanField(
                default=False,
                help_text="Driver asked for a full tank; litres are set at approval/dispense.",
            ),
        ),
        migrations.AddField(
            model_name="fuelrequest",
            name="driver_photo_base64",
            field=models.TextField(
                blank=True,
                help_text="Driver-submitted photo proof at MVFO creation (base64).",
            ),
        ),
        migrations.AddField(
            model_name="fuelrequest",
            name="efd_receipt_base64",
            field=models.TextField(
                blank=True,
                help_text="Electronic Fiscal Device receipt image from the driver (base64).",
            ),
        ),
        migrations.RunPython(migrate_kerosene_to_diesel, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="vehicle",
            name="default_fuel_type",
            field=models.CharField(
                choices=[("Diesel", "Diesel"), ("Petrol", "Petrol")],
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="fuelprice",
            name="fuel_type",
            field=models.CharField(
                choices=[("Diesel", "Diesel"), ("Petrol", "Petrol")],
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="fuelrequest",
            name="fuel_type",
            field=models.CharField(
                choices=[("Diesel", "Diesel"), ("Petrol", "Petrol")],
                max_length=16,
            ),
        ),
    ]
