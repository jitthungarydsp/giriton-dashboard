from dsp_kw import load_month_attendance
from dsp_googlesheet import create_statistics
from dsp_drivers_kw import load_drivers
from dsp_orders_kw import load_orders
from dsp_order_custmeres import load_order_customers
from dsp_statics_kw import create_daily_statistics,create_driver_statistics,calculate_arrival_status,create_driver_summary,create_attendance_route_statistics,create_earning_estimate
from dsp_common_kw import dsp_date_range, hu_time
from resources.courier_card_snapshot import safe_write_snapshot
from resources.dsp_month_archive import archive_current_dsp_months
from resources.source_sheet_sync import sync_source_sheets
from scripts.load_courier_master import sync_courier_master


def snapshot_month_from_run_range():
    start_date, end_date = dsp_date_range()

    if start_date.year == end_date.year and start_date.month == end_date.month:
        return start_date.strftime("%Y-%m")

    return None

if __name__ == "__main__":

    result = load_drivers()
    result = load_orders()
    result = load_order_customers()
    result = create_daily_statistics()
    result = create_driver_statistics()
    result = create_attendance_route_statistics()
    result = create_earning_estimate()
    result = calculate_arrival_status()
    result = create_driver_summary()
    try:
        source_sync_result = sync_source_sheets()
        print(
            {
                "source_sheet_sync": source_sync_result,
            }
        )
    except Exception as error:
        print(
            {
                "source_sheet_sync": "skipped",
                "error": str(error),
            }
        )

    try:
        courier_master_result = sync_courier_master()
        print(
            {
                "courier_master": courier_master_result,
            }
        )
    except Exception as error:
        print(
            {
                "courier_master": "skipped",
                "error": str(error),
            }
        )

    try:
        archive_result = archive_current_dsp_months()
        print(archive_result)
    except Exception as error:
        print(
            {
                "archive": "skipped",
                "error": str(error),
            }
        )

    try:
        result = safe_write_snapshot(
            month_text=snapshot_month_from_run_range(),
            preserve_existing=True
        )
    except Exception as error:
        result = {
            "snapshot": "skipped",
            "error": str(error),
        }

    print(result)
