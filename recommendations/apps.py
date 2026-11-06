from django.apps import AppConfig


class RecommendationsConfig(AppConfig):
    name = 'recommendations'

    def ready(self):
        from . import checks  # noqa: F401  (registers the deploy checks)
