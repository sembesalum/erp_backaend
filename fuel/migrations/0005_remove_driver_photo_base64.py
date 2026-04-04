# Driver proof is EFD only, submitted after COLLECTED (not at create).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("fuel", "0004_remove_kerosene_mvfo_evidence"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="fuelrequest",
            name="driver_photo_base64",
        ),
    ]
