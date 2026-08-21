from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user
from app import db, login_manager
from app.models import User


auth = Blueprint("auth", __name__)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@auth.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter(
            (db.func.lower(User.email) == identifier.lower()) |
            (db.func.lower(User.username) == identifier.lower())
        ).first()

        if user and user.check_password(password):
            if not user.is_active:
                flash("Your account has been banned. Please contact support.", "error")
                return render_template("auth/login.html")

            login_user(user)
            if user.username == "jimmy":
                return redirect(url_for("main.admin_dashboard"))
            return redirect(url_for("main.dashboard"))

        flash("Invalid login details.", "error")

    return render_template("auth/login.html")


@auth.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip().lower()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not full_name or not username or not email or not password:
            flash("Please complete all required fields.", "error")
            return render_template("auth/register.html")

        if User.query.filter_by(username=username).first():
            flash("Username already exists.", "error")
            return render_template("auth/register.html")

        if User.query.filter_by(email=email).first():
            flash("Email already exists.", "error")
            return render_template("auth/register.html")

        referral_code = f"SE{username[:20]}".upper()

        if User.query.filter_by(referral_code=referral_code).first():
            referral_code = f"SE{username[:16]}{User.query.count()}".upper()

        # Check optional referral code entered during registration.
        entered_referral = request.form.get("referral_code", "").strip()
        referrer = None

        if entered_referral:
            referrer = User.query.filter(
                db.func.lower(User.referral_code) == entered_referral.lower()
            ).first()

            if not referrer:
                flash("Invalid referral code.", "error")
                return render_template("auth/register.html")

        user = User(
            full_name=full_name,
            username=username,
            email=email,
            referral_code=referral_code,
            referred_by=referrer.id if referrer else None,
        )
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        login_user(user)
        return redirect(url_for("main.dashboard"))

    return render_template("auth/register.html")


@auth.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("main.home"))
