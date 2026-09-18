import os
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, request, redirect, url_for, session
from text_cleaner import TextCleaner
from werkzeug.security import generate_password_hash, check_password_hash
import joblib
import pandas as pd
import mysql.connector
from contextlib import contextmanager

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("FLASK_SECRET_KEY environment variable is not set")

model = joblib.load("hybrid_sentiment_analyzer_model.pkl")

# ── MySQL Config ──────────────────────────────────────────────────────────────

DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "localhost"),
    "user":     os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD"),
    "database": os.environ.get("DB_NAME", "hybrid_analyzer_db"),
}
if not DB_CONFIG["password"]:
    raise RuntimeError("DB_PASSWORD environment variable is not set")

# ── DB Helpers ────────────────────────────────────────────────────────────────

@contextmanager
def get_connection():
    """Yields a MySQL connection and guarantees it's closed afterward."""
    conn = mysql.connector.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Creates the database and users table if they don't exist yet."""
    conn = mysql.connector.connect(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
    )
    try:
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']}")
        cursor.execute(f"USE {DB_CONFIG['database']}")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id       INT          AUTO_INCREMENT PRIMARY KEY,
                email    VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL
            )
        """)
        conn.commit()
        cursor.close()
    finally:
        conn.close()

init_db()


def get_user(email: str):
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        return user


def create_user(email: str, password: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (email, password) VALUES (%s, %s)",
            (email, generate_password_hash(password)),
        )
        conn.commit()
        cursor.close()

# ── Auth Routes ───────────────────────────────────────────────────────────────

@app.route("/")
def home():
    if "user" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("analyze"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("analyze"))

    error = None
    active_tab = "login"

    if request.method == "POST":
        action   = request.form.get("action")
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if action == "register":
            active_tab = "register"
            if get_user(email):
                error = "An account with this email already exists. Please log in."
            else:
                create_user(email, password)
                session["user"] = email
                return redirect(url_for("analyze"))

        elif action == "login":
            active_tab = "login"
            user = get_user(email)
            if user and check_password_hash(user["password"], password):
                session["user"] = email
                return redirect(url_for("analyze"))
            else:
                error = "Incorrect email or password. Please try again."

    return render_template("login.html", error=error, active_tab=active_tab)


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

# ── Analyzer Route ────────────────────────────────────────────────────────────

@app.route("/analyze")
def analyze():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("index.html", user=session["user"])


@app.route("/predict", methods=["POST"])
def predict():
    if "user" not in session:
        return redirect(url_for("login"))

    try:
        vote     = int(request.form["vote"])
        verified = int(request.form["verified"])
    except (KeyError, ValueError):
        return render_template("index.html", result="Invalid input — please check your entries.", user=session["user"])

    review_text = request.form.get("review", "").strip()
    if not review_text:
        return render_template("index.html", result="Please enter a review to analyze.", user=session["user"])

    data = pd.DataFrame([{
        "vote":       vote,
        "verified":   verified,
        "reviewText": review_text,
    }])

    prediction = model.predict(data)[0]
    result = "Positive Sentiment 😄" if prediction == 1 else "Negative Sentiment 😠"
    return render_template("index.html", result=result, user=session["user"])


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")