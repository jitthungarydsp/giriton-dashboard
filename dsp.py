from dsp_kw import load_month_attendance
from dsp_googlesheet import create_statistics
from dsp_drivers_kw import load_drivers
from dsp_orders_kw import load_orders
from dsp_order_custmeres import load_order_customers
from dsp_statics_kw import create_daily_statistics,create_driver_statistics,calculate_arrival_status,create_driver_summary

if __name__ == "__main__":

    #result = load_drivers()
    #result = load_orders()
    #result = load_order_customers()
    #result = create_daily_statistics()
    #result = create_driver_statistics()
    #result = calculate_arrival_status()
    result = create_driver_summary()

    print(result)