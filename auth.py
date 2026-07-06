import re

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models import User, Transaction
from config import Config

auth_bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("lobby.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        if not USERNAME_RE.match(username):
            flash("ユーザー名は英数字とアンダースコアのみ、3〜20文字で入力してください。", "error")
            return render_template("register.html", signup_bonus=Config.SIGNUP_BONUS)

        if len(password) < 8:
            flash("パスワードは8文字以上で入力してください。", "error")
            return render_template("register.html", signup_bonus=Config.SIGNUP_BONUS)

        if password != password2:
            flash("パスワードが一致しません。", "error")
            return render_template("register.html", signup_bonus=Config.SIGNUP_BONUS)

        if User.query.filter_by(username=username).first():
            flash("そのユーザー名はすでに使われています。", "error")
            return render_template("register.html", signup_bonus=Config.SIGNUP_BONUS)

        user = User(username=username, balance=Config.SIGNUP_BONUS)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        db.session.add(Transaction(
            user_id=user.id, amount=Config.SIGNUP_BONUS, kind="signup",
            description="新規登録ボーナス"
        ))
        db.session.commit()

        login_user(user)
        flash(f"ようこそ、{username}さん。{Config.SIGNUP_BONUS:,} Embersを進呈しました。", "success")
        return redirect(url_for("lobby.index"))

    return render_template("register.html", signup_bonus=Config.SIGNUP_BONUS)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("lobby.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            flash("ユーザー名またはパスワードが正しくありません。", "error")
            return render_template("login.html")

        login_user(user)
        return redirect(url_for("lobby.index"))

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
