## WooCommerce Factor Generator

این پروژه فایل JSON سفارش ووکامرس را می‌گیرد و یک PDF مناسب چاپ A4 (RTL فارسی) تولید می‌کند که شامل:

- فاکتور فروش (Invoice)
- برگه بسته‌بندی (Packing Slip)

است.

### نصب

```bash
pip install -r requirements.txt
```

### تنظیمات `.env`

فایل `.env` در ریشه پروژه ساخته شده و شامل:

- اطلاعات فروشگاه (نام، تلفن، آدرس، **کدپستی فرستنده**)
- مسیر فونت فارسی (`FONT_PATH`)
- تنظیمات اتصال خودکار به WooCommerce
- داده‌های مشتری و محصولات فرضی برای تولید سفارش نمونه

متغیرهای اصلی فروشگاه در `.env`:

- `STORE_NAME` (نام فروشگاه)
- `STORE_PHONE`
- `STORE_ADDRESS`
- `STORE_POSTCODE`

### اتصال خودکار به WooCommerce

برای اینکه هر سفارش جدید به شکل خودکار فاکتور شود، این متغیرها را در `.env` پر کنید:

- `WOO_BASE_URL` (آدرس سایت وردپرس، بدون `/` انتهایی)
- `WOO_CONSUMER_KEY`
- `WOO_CONSUMER_SECRET`
- `WOO_ORDER_STATUSES` (مثال: `processing,on-hold`)
- `WOO_OUTPUT_DIR` (ریشه ذخیره PDFها)
- `WOO_STATE_FILE` (فایل نگهداری سفارش‌های پردازش‌شده)
- `WOO_POLL_INTERVAL_SECONDS` (فاصله بررسی سفارش‌های جدید)

اجرای یک‌باره سینک سفارش‌ها:

```bash
python generator.py --env-file .env --sync-woocommerce
```

اجرای دائم (Auto Polling):

```bash
python generator.py --env-file .env --sync-woocommerce --continuous
```

گزینه‌های کاربردی:

- `--poll-interval 30` برای override فاصله polling
- `--state-file ./custom_state.json` برای مسیر فایل state
- `--max-pages 10` برای تعداد صفحات سفارش که در هر دور خوانده می‌شود

### تولید سفارش نمونه از `.env`

```bash
python generator.py --env-file .env --generate-sample-order sample_order.json
```

این دستور بر اساس مقادیر `SAMPLE_*` و `SAMPLE_PRODUCTS` داخل `.env` یک JSON سفارش فرضی می‌سازد.

### تولید PDF نهایی از یک JSON

```bash
python generator.py sample_order.json output.pdf --env-file .env
```

اگر بخواهید مسیر فونت را مستقیم در CLI بدهید (و روی `.env` override کنید):

```bash
python generator.py sample_order.json output.pdf --env-file .env --font-path ./assets/fonts/YOUR_FONT.ttf
```

### تاریخ فاکتور

تاریخ سفارش که از ووکامرس دریافت می‌شود به تاریخ شمسی تبدیل می‌شود و در فاکتور نمایش داده می‌شود.

### منطق چیدمان هوشمند

1. ابتدا فقط HTML فاکتور رندر می‌شود.
2. ارتفاع واقعی آن با موتور Layout خود WeasyPrint اندازه‌گیری می‌شود.
3. اگر ارتفاع فاکتور کمتر از 70٪ ارتفاع A4 باشد، Packing Slip زیر همان فاکتور می‌آید.
4. اگر بیشتر باشد، Packing Slip با Page Break به صفحه دوم می‌رود.

### مسیر ذخیره خروجی

خروجی PDF به‌صورت خودکار داخل مسیر زیر ذخیره می‌شود (بر اساس تاریخ شمسی روز اجرا):

- `مسیر خروجی/سال/ماه/تاریخ_شمسی_شماره_سفارش.pdf`
  - مثال: `1404/12/14041205_1001.pdf`

اگر پوشه‌ها وجود نداشته باشند، خود برنامه آن‌ها را می‌سازد.
