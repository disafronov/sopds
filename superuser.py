import os

os.environ["DJANGO_SETTINGS_MODULE"] = "sopds.settings"
import django  # noqa: E402

django.setup()
# Django models must be imported after django.setup().
from django.contrib.auth.management.commands.createsuperuser import (  # noqa: E402
    get_user_model,
)

if get_user_model().objects.filter(username=os.environ.get("SOPDS_USER", "root")):
    print("Super user already exists. SKIPPING...")
else:
    print("Creating super user...")
    get_user_model()._default_manager.db_manager("default").create_superuser(
        username=os.environ.get("SOPDS_USER", "root"),
        email=os.environ.get("SOPDS_EMAIL", "root@localhost"),
        password=os.environ.get("SOPDS_PASSWORD", "Ab,12345"),
    )
