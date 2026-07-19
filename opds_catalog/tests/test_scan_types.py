"""Unit tests for ContainerEntry and ContainerDiscovery dataclasses."""

import unittest

from opds_catalog.scan_types import ContainerDiscovery, ContainerEntry


class ContainerEntryTestCase(unittest.TestCase):
    """Verify ContainerEntry construction and attribute access."""

    def test_create_entry(self) -> None:
        """ContainerEntry stores name and size."""
        entry = ContainerEntry(name="f.fb2-183066-183652.inp", size=4096)
        self.assertEqual(entry.name, "f.fb2-183066-183652.inp")
        self.assertEqual(entry.size, 4096)


class ContainerDiscoveryTestCase(unittest.TestCase):
    """Verify ContainerDiscovery construction with various field combinations."""

    def test_create_with_entries(self) -> None:
        """ContainerDiscovery stores a list of ContainerEntry objects."""
        entries = [
            ContainerEntry(name="a.inp", size=100),
            ContainerEntry(name="b.inp", size=200),
        ]
        disc = ContainerDiscovery(entries=entries)
        self.assertEqual(len(disc.entries), 2)
        self.assertEqual(disc.entries[0].name, "a.inp")
        self.assertIsNone(disc.inpx_format)
        self.assertFalse(disc.inpx_folders)
        self.assertIsNone(disc.error)

    def test_create_with_inpx_fields(self) -> None:
        """ContainerDiscovery carries INPX-specific metadata."""
        entries = [ContainerEntry(name="book.inp", size=500)]
        disc = ContainerDiscovery(
            entries=entries,
            inpx_format=["utf-8", "1"],
            inpx_folders=True,
        )
        self.assertEqual(disc.inpx_format, ["utf-8", "1"])
        self.assertTrue(disc.inpx_folders)

    def test_create_with_error(self) -> None:
        """ContainerDiscovery can carry an error string."""
        disc = ContainerDiscovery(entries=[], error="corrupt archive")
        self.assertEqual(disc.error, "corrupt archive")
        self.assertEqual(disc.entries, [])
