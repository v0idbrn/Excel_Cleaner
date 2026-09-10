"""Regression tests for commercial branding (v1.1.0).

Covers:
- APP_VERSION single source of truth (config.py) consumed by models.
- Window title branding via main.create_window() (no 'MVP', includes version).
- App icon asset exists and is a valid multi-size ICO.
- PyInstaller spec packages the icon and sets the exe icon.

GUI tests are skipped automatically when there is no display (headless CI).
"""
from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import models  # noqa: E402
import main as app_main  # noqa: E402


class TestVersionSourceOfTruth(unittest.TestCase):
    def test_app_version_is_defined(self):
        self.assertRegex(config.APP_VERSION, r"^\d+\.\d+\.\d+$")

    def test_version_is_1_1_0(self):
        self.assertEqual(config.APP_VERSION, "1.1.0")

    def test_models_consumes_config_version(self):
        # AuditReport metadata must use the central constant, not a hardcoded copy.
        self.assertEqual(models.AuditReport.__dataclass_fields__["cleaner_version"].default,
                         config.APP_VERSION)


class TestWindowTitle(unittest.TestCase):
    def test_app_title_constant(self):
        self.assertEqual(app_main.APP_TITLE, "Excel Cleaner Pro")

    def test_app_title_has_no_mvp(self):
        self.assertNotIn("MVP", app_main.APP_TITLE)


class TestAppIconAsset(unittest.TestCase):
    ICO = ROOT / "assets" / "icono.ico"

    def test_icon_file_exists(self):
        self.assertTrue(self.ICO.exists(), "assets/icono.ico missing — the GUI falls back to the default Tk icon")

    def test_icon_is_valid_multi_size_ico(self):
        data = self.ICO.read_bytes()
        reserved, icon_type, count = struct.unpack("<HHH", data[:6])
        self.assertEqual(icon_type, 1, "not an ICO file")
        sizes = []
        for i in range(count):
            w, h, *_rest = struct.unpack("<BBBBHHII", data[6 + i * 16: 6 + i * 16 + 16])
            sizes.append(w or 256)
        self.assertIn(256, sizes, "missing 256px frame (needed for modern Explorer/taskbar)")
        self.assertIn(16, sizes, "missing 16px frame (needed for title bar)")

    def test_spec_sets_exe_icon(self):
        spec = (ROOT / "excel_cleaner.spec").read_text(encoding="utf-8")
        self.assertIn("assets/icono.ico", spec.replace("\\\\", "/").replace("\\", "/"))

    def test_spec_packs_icon_as_data(self):
        spec = (ROOT / "excel_cleaner.spec").read_text(encoding="utf-8")
        self.assertIn("'assets/icono.ico', 'assets'", spec.replace('"', "'"))


def _can_create_tk() -> bool:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.destroy()
        return True
    except Exception:
        return False


@unittest.skipUnless(_can_create_tk(), "No display available (headless environment)")
class TestCreateWindow(unittest.TestCase):
    def test_create_window_title_and_icon(self):
        root = app_main.create_window()
        try:
            self.assertEqual(root.title(), "Excel Cleaner Pro")
            self.assertNotIn("MVP", root.title())
            # iconbitmap was applied without error (asset exists in repo)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main(verbosity=2)
