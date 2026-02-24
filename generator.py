#!/usr/bin/env python3
"""WooCommerce order to Persian A4 invoice + packing slip PDF generator."""

from __future__ import annotations

import argparse
import base64
import json
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


A4_HEIGHT_MM = 297.0
INVOICE_THRESHOLD_RATIO = 0.70
PX_TO_MM = 25.4 / 96.0


@dataclass(frozen=True)
class StoreInfo:
    name: str = "[نام فروشگاه]"
    phone: str = "[تلفن فروشگاه]"
    address: str = "[آدرس فروشگاه]"
    postcode: str = "[کد پستی فروشگاه]"


@dataclass(frozen=True)
class WooConfig:
    base_url: str
    consumer_key: str
    consumer_secret: str
    statuses: tuple[str, ...]
    output_dir: Path
    state_file: Path
    poll_interval_seconds: int


class OrderDocumentGenerator:
    """Render invoice + packing slip HTML and produce printable PDF."""

    def __init__(self, template_dir: Path, css_path: Path, font_path: Optional[Path] = None):
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )
        self.css_path = css_path
        self.font_path = font_path

    def render_html(self, template_name: str, context: Dict[str, Any]) -> str:
        template = self.env.get_template(template_name)
        return template.render(**context)

    def calculate_content_height_mm(self, html: str, content_id: str = "measure-root") -> float:
        """Measure rendered box height in mm using WeasyPrint layout engine."""
        from weasyprint import CSS, HTML

        document = HTML(string=html, base_url=str(Path.cwd())).render(stylesheets=[CSS(filename=str(self.css_path))])
        if not document.pages:
            return 0.0

        root_box = document.pages[0]._page_box
        target_box = self._find_box_by_id(root_box, content_id)
        if target_box is None:
            return 0.0
        return float(target_box.height) * PX_TO_MM

    def decide_layout(self, invoice_height_mm: float) -> str:
        threshold_mm = A4_HEIGHT_MM * INVOICE_THRESHOLD_RATIO
        return "same_page" if invoice_height_mm < threshold_mm else "new_page"

    def generate_pdf(self, html: str, output_path: Path) -> None:
        from weasyprint import CSS, HTML

        stylesheets = [CSS(filename=str(self.css_path))]
        HTML(string=html, base_url=str(Path.cwd())).write_pdf(str(output_path), stylesheets=stylesheets)

    def _find_box_by_id(self, box: Any, target_id: str) -> Optional[Any]:
        element = getattr(box, "element", None)
        if element is not None and element.get("id") == target_id:
            return box

        for child in getattr(box, "children", []):
            found = self._find_box_by_id(child, target_id)
            if found is not None:
                return found
        return None


def parse_dotenv(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        values[key] = value
    return values


def to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal("0")


def format_toman(value: Decimal) -> str:
    quantized = value.quantize(Decimal("1"))
    return f"{quantized:,}".replace(",", "٬")


def full_name(data: Dict[str, Any]) -> str:
    first = (data.get("first_name") or "").strip()
    last = (data.get("last_name") or "").strip()
    return f"{first} {last}".strip() or "—"


def join_non_empty(parts: Iterable[str], sep: str = "، ") -> str:
    return sep.join([p for p in (s.strip() for s in parts if s) if p])


def make_store_info(env_values: Dict[str, str]) -> StoreInfo:
    store_name = env_values.get("STORE_NAME", "[نام فروشگاه]")
    return StoreInfo(
        name=store_name,
        phone=env_values.get("STORE_PHONE", "[تلفن فروشگاه]"),
        address=env_values.get("STORE_ADDRESS", "[آدرس فروشگاه]"),
        postcode=env_values.get("STORE_POSTCODE", "[کد پستی فروشگاه]"),
    )


def make_woo_config(env_values: Dict[str, str], state_file_override: Optional[Path], poll_override: Optional[int]) -> WooConfig:
    base_url = env_values.get("WOO_BASE_URL", "").strip().rstrip("/")
    consumer_key = env_values.get("WOO_CONSUMER_KEY", "").strip()
    consumer_secret = env_values.get("WOO_CONSUMER_SECRET", "").strip()

    if not base_url or not consumer_key or not consumer_secret:
        raise SystemExit(
            "برای اتصال خودکار به ووکامرس باید WOO_BASE_URL و WOO_CONSUMER_KEY و WOO_CONSUMER_SECRET در .env تنظیم شوند."
        )

    statuses_raw = env_values.get("WOO_ORDER_STATUSES", "processing,on-hold").strip()
    statuses = tuple([s.strip() for s in statuses_raw.split(",") if s.strip()]) or ("processing", "on-hold")

    output_dir = Path(env_values.get("WOO_OUTPUT_DIR", "./output")).expanduser()
    state_file = state_file_override or Path(env_values.get("WOO_STATE_FILE", "./.woo_processed_orders.json")).expanduser()
    poll_interval_seconds = poll_override or int(env_values.get("WOO_POLL_INTERVAL_SECONDS", "60"))

    return WooConfig(
        base_url=base_url,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        statuses=statuses,
        output_dir=output_dir,
        state_file=state_file,
        poll_interval_seconds=max(5, poll_interval_seconds),
    )


def gregorian_to_jalali(year: int, month: int, day: int) -> tuple[int, int, int]:
    g_days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    j_days_in_month = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]

    gy = year - 1600
    gm = month - 1
    gd = day - 1

    g_day_no = 365 * gy + (gy + 3) // 4 - (gy + 99) // 100 + (gy + 399) // 400
    for i in range(gm):
        g_day_no += g_days_in_month[i]
    if gm > 1 and ((year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)):
        g_day_no += 1
    g_day_no += gd

    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053

    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461

    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365

    jm = 0
    while jm < 11 and j_day_no >= j_days_in_month[jm]:
        j_day_no -= j_days_in_month[jm]
        jm += 1

    jd = j_day_no + 1
    return jy, jm + 1, jd


def resolve_output_path(requested_output: Path, order_number: str, now: datetime) -> Path:
    jy, jm, jd = gregorian_to_jalali(now.year, now.month, now.day)
    base_dir = requested_output.parent if requested_output.suffix.lower() == ".pdf" else requested_output

    target_dir = base_dir / str(jy) / f"{jm:02d}"
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / f"{jy:04d}{jm:02d}{jd:02d}_{order_number}.pdf"


def format_jalali_datetime(value: str) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        jy, jm, jd = gregorian_to_jalali(dt.year, dt.month, dt.day)
        return f"{jy:04d}/{jm:02d}/{jd:02d} {dt:%H:%M}"
    except ValueError:
        return value


def normalize_order(order: Dict[str, Any], store: StoreInfo) -> Dict[str, Any]:
    billing = order.get("billing", {})
    shipping = order.get("shipping", {})
    line_items = order.get("line_items", [])

    rows = []
    total_items_count = 0
    subtotal = Decimal("0")

    for item in line_items:
        quantity = int(item.get("quantity") or 0)
        total_items_count += quantity

        line_total = to_decimal(item.get("total"))
        unit_price = (line_total / quantity) if quantity else Decimal("0")
        subtotal += line_total

        rows.append(
            {
                "name": item.get("name", "—"),
                "quantity": quantity,
                "unit_price": format_toman(unit_price),
                "line_total": format_toman(line_total),
            }
        )

    order_date_fa = format_jalali_datetime(order.get("date_created") or "")

    shipping_address = join_non_empty(
        [
            shipping.get("address_1", ""),
            shipping.get("address_2", ""),
            shipping.get("city", ""),
            shipping.get("state", ""),
        ]
    )

    return {
        "order_number": order.get("number") or order.get("id") or "—",
        "order_date": order_date_fa,
        "customer_name": full_name(billing),
        "customer_phone": billing.get("phone") or "—",
        "shipping_name": full_name(shipping),
        "shipping_phone": billing.get("phone") or "—",
        "shipping_postcode": shipping.get("postcode") or "—",
        "shipping_address": shipping_address or "—",
        "items": rows,
        "subtotal": format_toman(subtotal),
        "total": format_toman(to_decimal(order.get("total")) or subtotal),
        "customer_note": order.get("customer_note") or "",
        "total_items_count": total_items_count,
        "store": store,
    }


def build_final_html(generator: OrderDocumentGenerator, context: Dict[str, Any]) -> tuple[str, float, str]:
    invoice_partial = generator.render_html("invoice.html", context)
    measure_html = generator.render_html("measure.html", {"content": invoice_partial})

    invoice_height_mm = generator.calculate_content_height_mm(measure_html)
    layout = generator.decide_layout(invoice_height_mm)

    packing_partial = generator.render_html("packing_slip.html", context)
    final_html = generator.render_html(
        "document.html",
        {
            "invoice_html": invoice_partial,
            "packing_html": packing_partial,
            "layout": layout,
            "font_path": str(generator.font_path) if generator.font_path else None,
        },
    )
    return final_html, invoice_height_mm, layout


def parse_products_from_env(env_values: Dict[str, str]) -> list[Dict[str, Any]]:
    raw_products = env_values.get("SAMPLE_PRODUCTS", "")
    if not raw_products.strip():
        return [
            {"name": "ماسک سه لایه", "quantity": 2, "unit_price": 170000},
            {"name": "محلول ضدعفونی 500ml", "quantity": 5, "unit_price": 250000},
        ]

    products: list[Dict[str, Any]] = []
    for chunk in raw_products.split(";"):
        part = chunk.strip()
        if not part:
            continue
        pieces = [p.strip() for p in part.split("|")]
        if len(pieces) != 3:
            continue
        name, quantity, unit_price = pieces
        products.append(
            {
                "name": name,
                "quantity": int(quantity or 0),
                "unit_price": int(unit_price or 0),
            }
        )

    return products or [
        {"name": "ماسک سه لایه", "quantity": 2, "unit_price": 170000},
        {"name": "محلول ضدعفونی 500ml", "quantity": 5, "unit_price": 250000},
    ]


def generate_sample_order(env_values: Dict[str, str]) -> Dict[str, Any]:
    products = parse_products_from_env(env_values)
    line_items = []
    total = 0

    for idx, product in enumerate(products, start=1):
        quantity = int(product["quantity"])
        unit_price = int(product["unit_price"])
        line_total = quantity * unit_price
        total += line_total

        line_items.append(
            {
                "id": idx,
                "name": product["name"],
                "quantity": quantity,
                "total": str(line_total),
            }
        )

    return {
        "id": 1001,
        "number": env_values.get("SAMPLE_ORDER_NUMBER", "1001"),
        "date_created": datetime.now().isoformat(timespec="minutes"),
        "total": str(total),
        "customer_note": env_values.get("SAMPLE_CUSTOMER_NOTE", "تحویل در ساعات اداری"),
        "billing": {
            "first_name": env_values.get("SAMPLE_BILLING_FIRST_NAME", "مریم"),
            "last_name": env_values.get("SAMPLE_BILLING_LAST_NAME", "احمدی"),
            "phone": env_values.get("SAMPLE_BILLING_PHONE", "09120000000"),
        },
        "shipping": {
            "first_name": env_values.get("SAMPLE_SHIPPING_FIRST_NAME", "مریم"),
            "last_name": env_values.get("SAMPLE_SHIPPING_LAST_NAME", "احمدی"),
            "address_1": env_values.get("SAMPLE_SHIPPING_ADDRESS_1", "تهران، خیابان نمونه، پلاک ۱۲"),
            "address_2": env_values.get("SAMPLE_SHIPPING_ADDRESS_2", "واحد ۴"),
            "city": env_values.get("SAMPLE_SHIPPING_CITY", "تهران"),
            "state": env_values.get("SAMPLE_SHIPPING_STATE", "تهران"),
            "postcode": env_values.get("SAMPLE_SHIPPING_POSTCODE", "1111111111"),
        },
        "line_items": line_items,
    }


def create_generator(base_dir: Path, env_values: Dict[str, str], cli_font_path: Optional[Path]) -> OrderDocumentGenerator:
    resolved_font_path = cli_font_path
    if resolved_font_path is None and env_values.get("FONT_PATH"):
        resolved_font_path = Path(env_values["FONT_PATH"])

    return OrderDocumentGenerator(
        template_dir=base_dir / "templates",
        css_path=base_dir / "print.css",
        font_path=resolved_font_path,
    )


def generate_single_order_pdf(
    order: Dict[str, Any],
    store: StoreInfo,
    generator: OrderDocumentGenerator,
    output_root: Path,
) -> Path:
    context = normalize_order(order, store)
    output_path = resolve_output_path(output_root, str(context["order_number"]), datetime.now())
    final_html, _, _ = build_final_html(generator, context)
    generator.generate_pdf(final_html, output_path)
    return output_path


def load_processed_order_ids(state_file: Path) -> set[int]:
    if not state_file.exists():
        return set()
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    ids = data.get("processed_order_ids", [])
    return {int(i) for i in ids if str(i).isdigit()}


def save_processed_order_ids(state_file: Path, processed_ids: set[int]) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {"processed_order_ids": sorted(processed_ids)}
    state_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_woocommerce_orders(config: WooConfig, per_page: int, page: int) -> list[Dict[str, Any]]:
    params = {
        "per_page": str(per_page),
        "page": str(page),
        "orderby": "date",
        "order": "asc",
        "status": ",".join(config.statuses),
    }
    url = f"{config.base_url}/wp-json/wc/v3/orders?{urlencode(params)}"
    token = base64.b64encode(f"{config.consumer_key}:{config.consumer_secret}".encode("utf-8")).decode("ascii")
    req = Request(url, headers={"Authorization": f"Basic {token}", "Accept": "application/json"})

    try:
        with urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"WooCommerce API error {exc.code}: {exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"WooCommerce API connection error: {exc.reason}") from exc

    parsed = json.loads(body)
    if not isinstance(parsed, list):
        return []
    return [order for order in parsed if isinstance(order, dict)]


def sync_woocommerce_orders(
    config: WooConfig,
    store: StoreInfo,
    generator: OrderDocumentGenerator,
    continuous: bool,
    max_pages: int,
) -> None:
    processed_ids = load_processed_order_ids(config.state_file)

    while True:
        generated_count = 0

        for page in range(1, max_pages + 1):
            orders = fetch_woocommerce_orders(config, per_page=50, page=page)
            if not orders:
                break

            for order in orders:
                raw_order_id = order.get("id")
                if not isinstance(raw_order_id, int):
                    continue
                if raw_order_id in processed_ids:
                    continue

                pdf_path = generate_single_order_pdf(order, store, generator, config.output_dir)
                processed_ids.add(raw_order_id)
                save_processed_order_ids(config.state_file, processed_ids)
                generated_count += 1
                print(f"Generated invoice for order #{order.get('number', raw_order_id)} -> {pdf_path}")

            if len(orders) < 50:
                break

        print(f"Sync complete. New PDFs generated: {generated_count}")

        if not continuous:
            return

        print(f"Waiting {config.poll_interval_seconds}s for next poll...")
        time.sleep(config.poll_interval_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Persian invoice and packing slip PDF from WooCommerce order JSON.")
    parser.add_argument("input_json", type=Path, nargs="?", help="Path to WooCommerce order JSON file")
    parser.add_argument("output_pdf", type=Path, nargs="?", help="Path to output PDF file")
    parser.add_argument("--font-path", type=Path, default=None, help="Path to embedded Persian TTF/OTF font")
    parser.add_argument("--env-file", type=Path, default=Path(".env"), help="Path to .env configuration file")
    parser.add_argument(
        "--generate-sample-order",
        type=Path,
        default=None,
        help="Generate a sample WooCommerce order JSON from .env values and exit",
    )
    parser.add_argument("--sync-woocommerce", action="store_true", help="Fetch orders from WooCommerce and generate PDFs")
    parser.add_argument("--continuous", action="store_true", help="Keep polling WooCommerce forever")
    parser.add_argument("--poll-interval", type=int, default=None, help="Polling interval in seconds (override .env)")
    parser.add_argument("--state-file", type=Path, default=None, help="State file path for processed WooCommerce order IDs")
    parser.add_argument("--max-pages", type=int, default=5, help="Max pages to read from WooCommerce orders API per sync")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env_values = parse_dotenv(args.env_file)

    if args.generate_sample_order:
        sample_order = generate_sample_order(env_values)
        args.generate_sample_order.write_text(
            json.dumps(sample_order, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Sample order created: {args.generate_sample_order}")
        return

    base_dir = Path(__file__).parent
    store = make_store_info(env_values)

    if args.sync_woocommerce:
        config = make_woo_config(env_values, args.state_file, args.poll_interval)
        generator = create_generator(base_dir, env_values, args.font_path)
        sync_woocommerce_orders(config, store, generator, continuous=args.continuous, max_pages=max(1, args.max_pages))
        return

    if not args.input_json or not args.output_pdf:
        raise SystemExit("input_json و output_pdf لازم هستند (یا از --generate-sample-order/--sync-woocommerce استفاده کنید).")

    generator = create_generator(base_dir, env_values, args.font_path)
    order = json.loads(args.input_json.read_text(encoding="utf-8"))
    output_path = generate_single_order_pdf(order, store, generator, args.output_pdf)
    print(f"PDF created: {output_path}")


if __name__ == "__main__":
    main()
