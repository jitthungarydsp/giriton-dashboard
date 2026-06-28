import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROBOT_FILE = PROJECT_ROOT / "folgaltsag.robot"
RUN_DIR = PROJECT_ROOT / "results" / "robot_runs"
PID_FILE = RUN_DIR / "folgaltsag.pid"
LOG_FILE = RUN_DIR / "folgaltsag.log"


def ensure_run_dir():
    RUN_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def is_process_running(pid):
    if not pid:
        return False

    try:
        os.kill(
            pid,
            0,
        )
        return True
    except OSError:
        return False


def get_running_pid():
    if not PID_FILE.exists():
        return None

    try:
        pid = int(
            PID_FILE.read_text(
                encoding="utf-8"
            ).strip()
        )
    except ValueError:
        PID_FILE.unlink(
            missing_ok=True
        )
        return None

    if is_process_running(pid):
        return pid

    PID_FILE.unlink(
        missing_ok=True
    )
    return None


def read_log_tail(max_lines=180):
    if not LOG_FILE.exists():
        return ""

    lines = LOG_FILE.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines()

    return "\n".join(
        lines[-max_lines:]
    )


def start_robot():
    ensure_run_dir()

    if not ROBOT_FILE.exists():
        raise FileNotFoundError(
            f"Nem találom a robot fájlt: {ROBOT_FILE}"
        )

    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    with LOG_FILE.open(
        "w",
        encoding="utf-8",
        errors="replace",
    ) as log:
        log.write(
            f"Foglaltság robot indítva: {timestamp}\n"
        )
        log.write(
            f"Robot fájl: {ROBOT_FILE}\n\n"
        )
        log.flush()

        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "robot",
                "--outputdir",
                str(RUN_DIR),
                str(ROBOT_FILE),
            ],
            cwd=str(PROJECT_ROOT),
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP
                if os.name == "nt"
                else 0
            ),
        )

    PID_FILE.write_text(
        str(process.pid),
        encoding="utf-8",
    )

    return process.pid


def show_robots_page():
    st.title("Robotok")

    user = st.session_state["user"]

    if user.get("role") != "admin":
        st.error(
            "Ezt az oldalt csak admin indíthatja."
        )
        return

    ensure_run_dir()

    st.subheader("Foglaltság robot")
    st.caption(
        "A gomb a helyi gépen futtatja a folgaltsag.robot fájlt, és a results/robot_runs mappába írja a logokat."
    )

    running_pid = get_running_pid()

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Állapot",
        "Fut" if running_pid else "Nem fut",
    )
    c2.metric(
        "PID",
        running_pid or "-",
    )
    c3.metric(
        "Robot fájl",
        ROBOT_FILE.name,
    )

    if running_pid:
        st.warning(
            "A robot jelenleg fut. Várd meg, amíg befejezi, utána lehet újraindítani."
        )
    else:
        if st.button(
            "Foglaltság robot indítása",
            type="primary",
            use_container_width=True,
        ):
            try:
                pid = start_robot()
                st.success(
                    f"Robot elindítva. PID: {pid}"
                )
                st.rerun()
            except Exception as exc:
                st.error(
                    f"Robot indítás sikertelen: {exc}"
                )

    st.divider()

    st.subheader("Utolsó futás log")

    log_text = read_log_tail()

    if log_text:
        st.code(
            log_text,
            language="text",
        )
    else:
        st.info(
            "Még nincs robot log."
        )

    st.caption(
        f"Log mappa: {RUN_DIR}"
    )
