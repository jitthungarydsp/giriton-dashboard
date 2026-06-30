import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

from resources.github_actions import (
    GitHubActionsError,
    dispatch_robot,
    get_actions_url,
    get_config,
    get_latest_runs,
)

BUDAPEST_TZ = ZoneInfo("Europe/Budapest")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _status_label(run):
    status = run.get("status") or "-"
    conclusion = run.get("conclusion")

    if status == "completed":
        if conclusion == "success":
            return "Sikeres"
        if conclusion == "failure":
            return "Hibas"
        if conclusion == "cancelled":
            return "Megszakitva"
        if conclusion == "skipped":
            return "Kihagyva"
        if conclusion:
            return conclusion

    if status == "in_progress":
        return "Fut (GitHub szerint)"
    if status == "queued":
        return "Sorban"

    return status


def _format_github_time(value):
    if not value:
        return "-"

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError:
        return value

    return parsed.astimezone(BUDAPEST_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _show_run_table(runs):
    if not runs:
        st.info("Meg nincs lathato GitHub Actions futas.")
        return

    rows = []
    for run in runs:
        rows.append(
            {
                "ID": run.get("id"),
                "Allapot": _status_label(run),
                "Inditva": _format_github_time(run.get("created_at")),
                "Frissitve": _format_github_time(run.get("updated_at")),
                "Branch": run.get("head_branch", "-"),
                "Link": run.get("html_url", ""),
            }
        )

    st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
    )


def _trigger_button(
    label,
    *,
    run_folgaltsag=False,
    run_girition=False,
    run_dsp=False,
    run_raw_export=False,
    girition_start_date="",
    girition_days=10,
):
    if st.button(
        label,
        type="primary",
        use_container_width=True,
    ):
        try:
            result = dispatch_robot(
                run_folgaltsag=run_folgaltsag,
                run_girition=run_girition,
                run_dsp=run_dsp,
                run_raw_export=run_raw_export,
                girition_start_date=girition_start_date,
                girition_days=girition_days,
            )
            st.success(
                f"GitHub Actions inditva: {result['workflow']} / {result['ref']} / {result['triggered_at']}"
            )
        except GitHubActionsError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Varatlan hiba GitHub Actions inditasnal: {exc}")


def _copy_secret_to_env(env, secret_name):
    value = os.getenv(secret_name)
    if not value:
        try:
            value = st.secrets.get(secret_name)
        except Exception:
            value = None

    if value:
        env[secret_name] = str(value)


def _run_local_girition(start_date, days):
    timestamp = datetime.now(BUDAPEST_TZ).strftime("%Y%m%d-%H%M%S")
    output_dir = PROJECT_ROOT / "results" / f"local-girition-{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["GIRITION_START_DATE"] = str(start_date)
    env["GIRITION_DAYS"] = str(days)
    _copy_secret_to_env(env, "GIRITON_USER")
    _copy_secret_to_env(env, "GIRITON_PASSWORD")
    _copy_secret_to_env(env, "GIRITON_GOOGLE_CREDENTIALS_JSON")

    robot_cmd = [
        sys.executable,
        "-m",
        "robot",
        "--loglevel",
        "DEBUG",
        "--outputdir",
        str(output_dir),
        "--variable",
        f"RUN_START_DATE:{start_date}",
        "--variable",
        f"DAYS_TO_SYNC:{days}",
        "girition_github.robot",
    ]
    robot_result = subprocess.run(
        robot_cmd,
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60 * 30,
    )

    if robot_result.returncode != 0:
        raise RuntimeError(
            "A heti Girition lokal futtatas hibara ment.\n\n"
            f"{robot_result.stdout}\n{robot_result.stderr}"
        )

    sync_result = subprocess.run(
        [sys.executable, "update_shift_reconciliation.py"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60 * 5,
    )

    if sync_result.returncode != 0:
        raise RuntimeError(
            "A Muszak ellenorzes frissitese hibara ment.\n\n"
            f"{sync_result.stdout}\n{sync_result.stderr}"
        )

    return {
        "output_dir": str(output_dir),
        "robot_stdout": robot_result.stdout,
        "sync_stdout": sync_result.stdout,
    }


def _trigger_local_weekly_girition(start_date):
    if st.button(
        "Heti lekerdezes (helyi futas)",
        type="primary",
        use_container_width=True,
    ):
        try:
            with st.spinner("Heti Girition lekerdezes fut helyben..."):
                result = _run_local_girition(start_date, 7)
            st.success(
                f"Heti Girition lokal futas kesz. Eredmenyek: {result['output_dir']}"
            )
            if result.get("sync_stdout"):
                st.code(result["sync_stdout"][-2000:])
        except Exception as exc:
            st.error(str(exc))


def show_robots_page():
    st.title("Robotok")

    user = st.session_state["user"]

    if user.get("role") != "admin":
        st.error("Ezt az oldalt csak admin indithatja.")
        return

    config = get_config()
    actions_url = get_actions_url()

    st.caption(
        "Az 1 napos Girition, a Foglaltsag es a DSP GitHub Actionsben fut. A heti Girition lekerdezes helyben, a Streamlit szerveren fut."
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Repository", f"{config['owner']}/{config['repo']}")
    c2.metric("Workflow", config["workflow"])
    c3.metric("Branch", config["ref"])

    st.markdown(f"[GitHub Actions megnyitasa]({actions_url})")

    st.divider()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("Foglaltsag")
        st.caption("A `folgaltsag_github.robot` futasat inditja GitHub Actionsben.")
        _trigger_button(
            "Foglaltsag robot inditasa",
            run_folgaltsag=True,
        )

    with col2:
        st.subheader("Girition")
        girition_date = st.date_input(
            "Lekerdezes kezdo napja",
            value=datetime.now(BUDAPEST_TZ).date(),
            key="girition_robot_start_date",
        )
        girition_start_date = girition_date.strftime("%Y-%m-%d")
        st.caption("A GitHubos frissites a Shift Subs es az Attendance adatot is frissiti.")
        st.info("Az Aktualis nap gomb GitHub Actionsben futtatja a nyers Giriton + Attendance exportot.")
        _trigger_button(
            "Giriton + Attendance frissitese",
            run_raw_export=True,
            girition_start_date=girition_start_date,
            girition_days=10,
        )
        _trigger_button(
            "Aktualis nap lekerdezese",
            run_raw_export=True,
            girition_start_date=girition_start_date,
            girition_days=1,
        )
        _trigger_local_weekly_girition(girition_start_date)

    with col3:
        st.subheader("DSP")
        st.caption("A `dsp.py` statisztika futasat inditja GitHub Actionsben.")
        _trigger_button(
            "DSP futtatasa",
            run_dsp=True,
        )

    st.divider()

    st.subheader("Legutobbi GitHub futasok")

    if st.button(
        "Allapot frissitese",
        use_container_width=True,
    ):
        st.rerun()

    try:
        _show_run_table(
            get_latest_runs()
        )
    except GitHubActionsError as exc:
        st.warning(str(exc))
    except Exception as exc:
        st.warning(f"Nem sikerult lekerni a GitHub futasokat: {exc}")

    st.info(
        "Szukseges Streamlit secret: `GITHUB_ACTIONS_TOKEN`. Fine-grained tokennel legyen Actions: Read and write jogosultsag erre a repositoryra."
    )
