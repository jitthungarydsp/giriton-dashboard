from dsp_kw import load_month_attendance
from dsp_googlesheet import create_statistics
from dsp_drivers_kw import load_drivers
from dsp_orders_kw import load_orders
from dsp_order_custmeres import load_order_customers
from dsp_statics_kw import create_daily_statistics,create_driver_statistics,calculate_arrival_status,create_driver_summary,create_attendance_route_statistics,create_earning_estimate
from dsp_common_kw import dsp_date_range, hu_time
from resources.courier_card_snapshot import safe_write_snapshot
from resources.dsp_month_archive import archive_current_dsp_months


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
