from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("webdata", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="extractedparameter",
            name="unit",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="parametersource",
            name="source_location",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
