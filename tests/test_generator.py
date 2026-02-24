import tempfile
import unittest
from pathlib import Path

from generator import (
    StoreInfo,
    WooConfig,
    load_processed_order_ids,
    make_store_info,
    make_woo_config,
    parse_dotenv,
    save_processed_order_ids,
)


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


class TestWooSyncConfig(unittest.TestCase):
    def test_make_woo_config_reads_env(self):
        env_values = {
            "WOO_BASE_URL": "https://example.com/",
            "WOO_CONSUMER_KEY": "ck_test",
            "WOO_CONSUMER_SECRET": "cs_test",
            "WOO_ORDER_STATUSES": "processing,on-hold",
            "WOO_OUTPUT_DIR": "./output",
            "WOO_STATE_FILE": "./state.json",
            "WOO_POLL_INTERVAL_SECONDS": "45",
        }
        config = make_woo_config(env_values, None, None)
        self.assertIsInstance(config, WooConfig)
        self.assertEqual(config.base_url, "https://example.com")
        self.assertEqual(config.poll_interval_seconds, 45)
        self.assertEqual(config.statuses, ("processing", "on-hold"))

    def test_state_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            save_processed_order_ids(state_path, {1001, 1003})
            loaded = load_processed_order_ids(state_path)
            self.assertEqual(loaded, {1001, 1003})


if __name__ == "__main__":
    unittest.main()
