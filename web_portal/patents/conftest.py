# This fixture applies to every patent test in this directory.
import pytest


@pytest.fixture(autouse=True)
def in_memory_uploaded_file_storage(settings):
    # Keep uploaded test files in memory instead of writing to the app's media store.
    # Preserve Django's standard static-file storage because tests may still reference it.
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
