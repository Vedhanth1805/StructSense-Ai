from django.apps import AppConfig
class WebdataConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "webdata"

    def ready(self):
        from . import signals  # noqa: F401
