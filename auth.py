import re
import secrets
import string

from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models import User, Transaction, utcnow
from config import Config
from notifications import notify

auth_bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")


def _generate_captcha(session_key="captcha_target"):
    """
    マクロ・自動化ツールによる不正行為(無限アカウント作成・動画の自動アップロード・
    動画の自動再生による収益稼ぎなど)を防ぐための簡易CAPTCHA。
    6文字のランダムなローマ字(大文字)を「お手本」として表示し、
    5つの選択肢の中から、お手本と完全に一致するものを選んでもらう。
    正解はセッション(サーバー側)に保存し、フォームの値を書き換えられても
    突破できないようにする。session_keyを変えることで、複数箇所(登録・動画アップロード・
    動画視聴など)で同時に使っても、それぞれの正解が混ざらないようにしている。
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

    session[session_key] = target
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

        raw_referrer = User.query.filter_by(referral_code=ref_code).first() if ref_code else None
        # 招待する側(紹介者)がDiscord連携済みでない場合、この紹介コードは無効として扱う
        # (招待する側・される側の両方がDiscord連携して初めて、紹介として成立させるため)
        referrer = raw_referrer if (raw_referrer and raw_referrer.discord_id) else None
        referrer_code_invalid = bool(ref_code) and raw_referrer and not raw_referrer.discord_id

        signup_bonus = Config.SIGNUP_BONUS  # 紹介ボーナスは、この時点ではまだ付与しない(Discord連携完了後に付与)

        user = User(
            username=username, balance=signup_bonus, referral_code=_generate_referral_code(),
            referred_by_id=referrer.id if referrer else None,
            referral_bonus_pending=bool(referrer),  # 紹介経由の場合、自分がDiscord連携したらボーナスが付与される
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        db.session.add(Transaction(
            user_id=user.id, amount=signup_bonus, kind="signup",
            description="新規登録ボーナス"
        ))

        if referrer:
            # 同じ人が短時間に大量の招待を成立させている場合、不正な自作自演の疑いとして検知する
            from datetime import timedelta
            recent_referrals = User.query.filter(
                User.referred_by_id == referrer.id, User.created_at >= utcnow() - timedelta(minutes=10)
            ).count()
            if recent_referrals >= 5:
                from fraud_detection import check_and_flag
                check_and_flag(referrer.id, "referral_burst", f"直近10分で{recent_referrals}件の招待が成立")

        db.session.commit()

        login_user(user)

        try:
            from fraud_detection import track_login_ip
            track_login_ip(user)
        except Exception:
            pass

        if referrer:
            flash(f"ようこそ、{username}さん。{signup_bonus:,} Embersを進呈しました。あなた自身がDiscord連携すると、紹介ボーナスも受け取れます。", "success")
        elif referrer_code_invalid:
            flash(f"ようこそ、{username}さん。{signup_bonus:,} Embersを進呈しました。なお、入力された紹介コードは、紹介者がDiscord未連携のため今回は適用されませんでした。", "success")
        else:
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

        try:
            from fraud_detection import track_login_ip
            track_login_ip(user)
        except Exception:
            pass  # IP記録に失敗しても、ログイン自体は成功させる

        return redirect(url_for("lobby.index"))

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
