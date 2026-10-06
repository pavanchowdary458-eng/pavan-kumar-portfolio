from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def home():
    message = ""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        msg = request.form.get("message", "").strip()
        if name and email and msg:
            message = f"Thanks, {name}! Your message has been received."
        else:
            message = "Please fill in all contact fields."
    return render_template("index.html", message=message)

if __name__ == "__main__":
    app.run(debug=True)
