import os
from io import StringIO

from django.core.management import call_command
from django.test import TestCase


class constanceTestCase(TestCase):
    test_module_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_ROOTLIB = os.path.join(test_module_path, "tests/data")

    def setUp(self) -> None:
        pass

    def test_constance_attributes_count(self) -> None:
        out = StringIO()
        call_command("constance", "list", stdout=out)
        out.seek(0)
        self.assertEqual(out.getvalue().count("\n"), 26)
        out.close()
