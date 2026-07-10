import re
import secrets

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models import User, Transaction
from config import Config
from notifications import notify

auth_bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")


def _generate_referral_code():
    while True:
        code = secrets.token_hex(4).upper()  # 8文字
        if not User.query.filter_by(referral_code=code).first():
            return code


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("lobby.index"))

    ref_code = request.args.get("ref", "").strip() or request.form.get("ref_code", "").strip()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        if not USERNAME_RE.match(username):
            flash("ユーザー名は英数字とアンダースコアのみ、3〜20文字で入力してください。", "error")
            return render_template("register.html", signup_bonus=Config.SIGNUP_BONUS, ref_code=ref_code)

        if len(password) < 8:
            flash("パスワードは8文字以上で入力してください。", "error")
            return render_template("register.html", signup_bonus=Config.SIGNUP_BONUS, ref_code=ref_code)

        if password != password2:
            flash("パスワードが一致しません。", "error")
            return render_template("register.html", signup_bonus=Config.SIGNUP_BONUS, ref_code=ref_code)

        if User.query.filter_by(username=username).first():
            flash("そのユーザー名はすでに使われています。", "error")
            return render_template("register.html", signup_bonus=Config.SIGNUP_BONUS, ref_code=ref_code)

        referrer = User.query.filter_by(referral_code=ref_code).first() if ref_code else None

        signup_bonus = Config.SIGNUP_BONUS + (Config.REFERRAL_BONUS_NEW if referrer else 0)

        user = User(
            username=username, balance=signup_bonus, referral_code=_generate_referral_code(),
            referred_by_id=referrer.id if referrer else None
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        db.session.add(Transaction(
            user_id=user.id, amount=signup_bonus, kind="signup",
            description="新規登録ボーナス" + ("(紹介ボーナス込み)" if referrer else "")
        ))

        if referrer:
            referrer.balance += Config.REFERRAL_BONUS_REFERRER
            db.session.add(Transaction(
                user_id=referrer.id, amount=Config.REFERRAL_BONUS_REFERRER, kind="referral",
                description=f"{username} を紹介"
            ))
            notify(referrer.id, f"{username} があなたの紹介コードで登録しました。{Config.REFERRAL_BONUS_REFERRER:,} Embersを獲得しました。")

        db.session.commit()

        login_user(user)
        flash(f"ようこそ、{username}さん。{signup_bonus:,} Embersを進呈しました。", "success")
        return redirect(url_for("lobby.index"))

    return render_template("register.html", signup_bonus=Config.SIGNUP_BONUS, ref_code=ref_code)


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
