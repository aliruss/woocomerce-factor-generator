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
- داده‌های مشتری و محصولات فرضی برای تولید سفارش نمونه

است.

### تولید سفارش نمونه از `.env`

```bash
python generator.py --env-file .env --generate-sample-order sample_order.json
```

این دستور بر اساس مقادیر `SAMPLE_*` و `SAMPLE_PRODUCTS` داخل `.env` یک JSON سفارش فرضی می‌سازد.

### تولید PDF نهایی

```bash
python generator.py sample_order.json output.pdf --env-file .env
```

اگر بخواهید مسیر فونت را مستقیم در CLI بدهید (و روی `.env` override کنید):

```bash
python generator.py sample_order.json output.pdf --env-file .env --font-path ./assets/fonts/YOUR_FONT.ttf
```

### منطق چیدمان هوشمند

1. ابتدا فقط HTML فاکتور رندر می‌شود.
2. ارتفاع واقعی آن با موتور Layout خود WeasyPrint اندازه‌گیری می‌شود.
3. اگر ارتفاع فاکتور کمتر از 70٪ ارتفاع A4 باشد، Packing Slip زیر همان فاکتور می‌آید.
4. اگر بیشتر باشد، Packing Slip با Page Break به صفحه دوم می‌رود.

### ساختار

- `generator.py`: منطق اصلی پردازش JSON، اندازه‌گیری ارتفاع، تصمیم layout و تولید PDF
- `templates/invoice.html`: قالب فاکتور
- `templates/packing_slip.html`: قالب برگه ارسال
- `templates/document.html`: مونتاژ نهایی صفحات
- `templates/measure.html`: قالب اندازه‌گیری ارتفاع فاکتور
- `print.css`: استایل چاپ (A4, RTL, mm-based)
