import re
import secrets
import string

from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models import User, Transaction
from config import Config
from notifications import notify

auth_bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")


def _generate_captcha():
    """
    マクロ・自動化ツールによる無限アカウント作成(招待の不正稼ぎ)を防ぐための簡易CAPTCHA。
    6文字のランダムなローマ字(大文字)を「お手本」として表示し、
    5つの選択肢の中から、お手本と完全に一致するものを選んでもらう。
    正解はセッション(サーバー側)に保存し、フォームの値を書き換えられても
    突破できないようにする。
    """
    target = "".join(secrets.choice(string.ascii_uppercase) for _ in range(6))

    def scramble(base):
        # お手本を少しだけ変えた「紛らわしい」ダミーの選択肢を作る(1〜3文字を別の文字に置き換える)
        chars = list(base)
        change_count = secrets.randbelow(3) + 1
        positions = secrets.SystemRandom().sample(range(len(chars)), change_count)
        for pos in positions:
            chars[pos] = secrets.choice(string.ascii_uppercase)
        return "".join(chars)

    options = {target}
    while len(options) < 5:
        options.add(scramble(target))
    options = list(options)
    secrets.SystemRandom().shuffle(options)

    session["captcha_target"] = target
    return target, options


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

    def render_with_fresh_captcha():
        target, options = _generate_captcha()
        return render_template(
            "register.html", signup_bonus=Config.SIGNUP_BONUS, ref_code=ref_code,
            captcha_target=target, captcha_options=options,
        )

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        captcha_answer = request.form.get("captcha_answer", "").strip()

        # マクロ・自動化ツールによる無限アカウント作成(招待の不正稼ぎ)を防ぐための本人確認。
        # 正解はサーバー側のセッションに保存してあるものと照合するため、フォームの値を
        # 直接書き換えても突破できない。
        correct_answer = session.pop("captcha_target", None)
        if not correct_answer or captcha_answer != correct_answer:
            flash("画像の確認に失敗しました。表示されたローマ字と一致するものを選び直してください。", "error")
            return render_with_fresh_captcha()

        if not USERNAME_RE.match(username):
            flash("ユーザー名は英数字とアンダースコアのみ、3〜20文字で入力してください。", "error")
            return render_with_fresh_captcha()

        if len(password) < 8:
            flash("パスワードは8文字以上で入力してください。", "error")
            return render_with_fresh_captcha()

        if password != password2:
            flash("パスワードが一致しません。", "error")
            return render_with_fresh_captcha()

        if User.query.filter_by(username=username).first():
            flash("そのユーザー名はすでに使われています。", "error")
            return render_with_fresh_captcha()

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

    target, options = _generate_captcha()
    return render_template(
        "register.html", signup_bonus=Config.SIGNUP_BONUS, ref_code=ref_code,
        captcha_target=target, captcha_options=options,
    )


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
