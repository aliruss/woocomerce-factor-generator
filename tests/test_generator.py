import unittest
from pathlib import Path

from generator import StoreInfo, make_store_info, parse_dotenv


class TestWatermarkRemovalRegression(unittest.TestCase):
    def test_make_store_info_does_not_require_watermark_variables(self):
        env_values = {
            "STORE_NAME": "فروشگاه تست",
            "STORE_PHONE": "02100000000",
            "STORE_ADDRESS": "آدرس تست",
            "STORE_POSTCODE": "1234567890",
        }

        store = make_store_info(env_values)

        self.assertEqual(
            store,
            StoreInfo(
                name="فروشگاه تست",
                phone="02100000000",
                address="آدرس تست",
                postcode="1234567890",
            ),
        )

    def test_store_info_has_no_watermark_fields(self):
        field_names = set(StoreInfo.__dataclass_fields__.keys())
        self.assertNotIn("watermark_enabled", field_names)
        self.assertNotIn("watermark_text", field_names)
        self.assertNotIn("watermark_font_size_mm", field_names)
        self.assertNotIn("watermark_opacity", field_names)
        self.assertNotIn("watermark_rotation_deg", field_names)

    def test_parse_dotenv_ignores_missing_file(self):
        env_values = parse_dotenv(Path("tests/does-not-exist.env"))
        self.assertEqual(env_values, {})


if __name__ == "__main__":
    unittest.main()
