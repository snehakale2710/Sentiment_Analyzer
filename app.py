import os
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, request, redirect, url_for, session
from text_cleaner import TextCleaner
from werkzeug.security import generate_password_hash, check_password_hash
import joblib
import pandas as pd
import mysql.connector
from mysql.connector import IntegrityError
from contextlib import contextmanager

app = Flask(__name__, static_folder="public/static", static_url_path="/static")
app.secret_key = os.environ.get("FLASK_SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("FLASK_SECRET_KEY environment variable is not set")

MIN_PASSWORD_LENGTH = 6

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
model = joblib.load(os.path.join(BASE_DIR, "hybrid_sentiment_analyzer_model.pkl"))

# ── MySQL Config ──────────────────────────────────────────────────────────────

DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "localhost"),
    "user":     os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD"),
    "database": os.environ.get("DB_NAME", "hybrid_analyzer_db"),
    "ssl_disabled": os.environ.get("DB_SSL_DISABLED", "0") == "1",
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
    """Creates the users table if it doesn't exist yet.
    Run only when RUN_DB_INIT=1 — on Vercel the database and its
    permissions are set up ahead of time (see database_setup.sql),
    since the app's DB user typically can't CREATE DATABASE there."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id       INT          AUTO_INCREMENT PRIMARY KEY,
                email    VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL
            )
        """)
        conn.commit()
        cursor.close()

if os.environ.get("RUN_DB_INIT") == "1":
    init_db()


def get_user(email: str):
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        return user


def create_user(email: str, password: str):
    """Returns True on success, False if the email was taken by a
    concurrent request (race between get_user() and this insert)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO users (email, password) VALUES (%s, %s)",
                (email, generate_password_hash(password)),
            )
            conn.commit()
            return True
        except IntegrityError:
            conn.rollback()
            return False
        finally:
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
            if not email or "@" not in email:
                error = "Please enter a valid email address."
            elif len(password) < MIN_PASSWORD_LENGTH:
                error = f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
            elif get_user(email):
                error = "An account with this email already exists. Please log in."
            elif not create_user(email, password):
                error = "An account with this email already exists. Please log in."
            else:
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

    if vote < 0 or verified not in (0, 1):
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