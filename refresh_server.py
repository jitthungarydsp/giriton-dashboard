from flask import Flask
import subprocess

app = Flask(__name__)

@app.route("/refresh-today")
def refresh_today():

    subprocess.Popen(
        ["python", "dsp.py", "--today"]
    )

    return "DSP indítva"

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000
    )