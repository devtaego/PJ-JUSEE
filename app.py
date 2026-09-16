from flask import Flask, render_template, request

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/setting")
def setting():
    return render_template("setting.html")


@app.route("/start", methods=["POST"])
def start():
    days = request.form["days"]
    cycle = request.form["cycle"]
    volatility = request.form["volatility"]

    return render_template(
        "invest.html",
        days=days,
        cycle=cycle,
        volatility=volatility
    )


if __name__ == "__main__":
    app.run(debug=True)