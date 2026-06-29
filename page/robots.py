import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

from resources.github_actions import (
    GitHubActionsError,
    dispatch_robot,
    get_actions_url,
    get_config,
    get_latest_runs,
)

BUDAPEST_TZ = ZoneInfo("Europe/Budapest")


def _status_label(run):
    status = run.get("status") or "-"
    conclusion = run.get("conclusion")

    if status == "completed":
        if conclusion == "success":
            return "Sikeres"
        if conclusion == "failure":
            return "Hibás"
        if conclusion == "cancelled":
            return "Megszakítva"
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
        st.info("Még nincs látható GitHub Actions futás.")
        return

    rows = []
    for run in runs:
        rows.append(
            {
                "ID": run.get("id"),
                "Állapot": _status_label(run),
                "Indítva": _format_github_time(run.get("created_at")),
                "Frissítve": _format_github_time(run.get("updated_at")),
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
                girition_start_date=girition_start_date,
                girition_days=girition_days,
            )
            st.success(
                f"GitHub Actions indítva: {result['workflow']} / {result['ref']} / {result['triggered_at']}"
            )
        except GitHubActionsError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Váratlan hiba GitHub Actions indításnál: {exc}")


def show_robots_page():
    st.title("Robotok")

    user = st.session_state["user"]

    if user.get("role") != "admin":
        st.error("Ezt az oldalt csak admin indíthatja.")
        return

    config = get_config()
    actions_url = get_actions_url()

    st.caption(
        "A robotok most már nem a Streamlit gépén futnak, hanem GitHub Actions workflow_dispatch indítással."
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Repository", f"{config['owner']}/{config['repo']}")
    c2.metric("Workflow", config["workflow"])
    c3.metric("Branch", config["ref"])

    st.markdown(f"[GitHub Actions megnyitása]({actions_url})")

    st.divider()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("Foglaltság")
        st.caption("A `folgaltsag_github.robot` futását indítja.")
        _trigger_button(
            "Foglaltság robot indítása",
            run_folgaltsag=True,
        )

    with col2:
        st.subheader("Girition")
        girition_date = st.date_input(
            "Lekérdezés kezdő napja",
            value=datetime.now(BUDAPEST_TZ).date(),
            key="girition_robot_start_date",
        )
        girition_start_date = girition_date.strftime("%Y-%m-%d")
        st.caption("A GitHub workflow-ban a `girition.robot` fut.")
        _trigger_button(
            "Girition robot indítása",
            run_girition=True,
        )
        _trigger_button(
            "Aktuális nap lekérdezése",
            run_girition=True,
            girition_start_date=girition_start_date,
            girition_days=1,
        )
        _trigger_button(
            "Heti lekérdezés",
            run_girition=True,
            girition_start_date=girition_start_date,
            girition_days=7,
        )

    with col3:
        st.subheader("DSP")
        st.caption("A `dsp.py` statisztika futását indítja.")
        _trigger_button(
            "DSP futtatása",
            run_dsp=True,
        )

    st.divider()

    st.subheader("Legutóbbi GitHub futások")

    if st.button(
        "Állapot frissítése",
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
        st.warning(f"Nem sikerült lekérni a GitHub futásokat: {exc}")

    st.info(
        "Szükséges Streamlit secret: `GITHUB_ACTIONS_TOKEN`. Fine-grained tokennél legyen Actions: Read and write jogosultság erre a repositoryra."
    )
