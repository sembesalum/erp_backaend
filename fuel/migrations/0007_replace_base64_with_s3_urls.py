# Generated manually to move image storage from base64 text columns to S3 URL columns.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fuel", "0006_driver_proof_and_reference_format"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="fuelrequest",
            name="pump_meter_photo_base64",
        ),
        migrations.RemoveField(
            model_name="fuelrequest",
            name="efd_receipt_base64",
        ),
        migrations.RemoveField(
            model_name="fuelrequest",
            name="fuel_level_photo_base64",
        ),
        migrations.RemoveField(
            model_name="fuelrequest",
            name="odometer_photo_base64",
        ),
        migrations.RemoveField(
            model_name="fuelrequest",
            name="driver_pump_photo_base64",
        ),
        migrations.AddField(
            model_name="fuelrequest",
            name="pump_meter_photo_url",
            field=models.URLField(
                blank=True,
                help_text="S3 URL for station/Simba pump meter image.",
            ),
        ),
        migrations.AddField(
            model_name="fuelrequest",
            name="efd_receipt_url",
            field=models.URLField(
                blank=True,
                help_text="S3 URL for EFD fiscal receipt image from the driver after COLLECTED.",
            ),
        ),
        migrations.AddField(
            model_name="fuelrequest",
            name="fuel_level_photo_url",
            field=models.URLField(
                blank=True,
                help_text="S3 URL for driver-submitted fuel level photo at MVFO creation.",
            ),
        ),
        migrations.AddField(
            model_name="fuelrequest",
            name="odometer_photo_url",
            field=models.URLField(
                blank=True,
                help_text="S3 URL for driver-submitted odometer photo at completion stage.",
            ),
        ),
        migrations.AddField(
            model_name="fuelrequest",
            name="driver_pump_photo_url",
            field=models.URLField(
                blank=True,
                help_text="S3 URL for optional driver-submitted pump photo at completion stage.",
            ),
        ),
    ]
