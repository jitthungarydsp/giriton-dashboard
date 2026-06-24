import requests

from datetime import datetime


def load_attendance():

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    url = (
        f"https://uftplslamjbbhlozsygo.supabase.co/functions/v1/"
        f"fetch-attendance/JIT/{today}"
        f"?organizationId=f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
    )

    return requests.get(
        url,
        timeout=30
    ).json()
    
def load_driver_details(driver_id):

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    url = (
        f"https://uftplslamjbbhlozsygo.supabase.co/functions/v1/"
        f"fetch-drivers-detail/{driver_id}/{today}"
        f"?organizationId=f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
    )

    return requests.get(
        url,
        timeout=30
    ).json()