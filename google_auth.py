"""
Google(Gmail)アカウント連携(OAuth2)。「Gmailでログイン」機能。

重要: この仕組みでは、ユーザーのGoogleパスワードやトークンを一切受け取らない。
「Gmailでログイン」を押すと、Google公式のサイトに移動し、そこでユーザー自身が
許可すると、Googleから「本人確認用の一時的な認可コード」だけがこのサイトに渡される。
それをGoogleのサーバーへ送り返して、初めて限定的なアクセストークン(メールアドレス・
氏名を読み取れるだけの権限)が発行される。パスワードは常にGoogle側で入力され、
このサイトのサーバーには一切届かない。
"""
import secrets

import requests
from flask import Blueprint, redirect, url_for, request, flash, session
from flask_login import login_required, current_user

from extensions import db
from config import Config
from models import User

google_auth_bp = Blueprint("google_auth", __name__)

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def google_oauth_configured():
    return bool(Config.GOOGLE_CLIENT_ID and Config.GOOGLE_CLIENT_SECRET and Config.GOOGLE_REDIRECT_URI)


@google_auth_bp.route("/google/login")
@login_required
def google_login():
    """「Gmailでログイン(連携)」ボタンから呼ばれる。Google公式の認可画面へリダイレクトする"""
    if not google_oauth_configured():
        flash("現在、Google連携は準備中です(管理者による設定が必要です)。", "error")
        return redirect(url_for("profile.index"))

    state = secrets.token_urlsafe(24)
    session["google_oauth_state"] = state

    params = {
        "client_id": Config.GOOGLE_CLIENT_ID,
        "redirect_uri": Config.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",  # メールアドレス・氏名だけを読み取る、最小限の権限
        "state": state,
        "prompt": "select_account",
    }
    query = "&".join(f"{k}={requests.utils.quote(v)}" for k, v in params.items())
    return redirect(f"{GOOGLE_AUTHORIZE_URL}?{query}")


@google_auth_bp.route("/google/callback")
@login_required
def google_callback():
    if not google_oauth_configured():
        flash("現在、Google連携は準備中です。", "error")
        return redirect(url_for("profile.index"))

    if request.args.get("error"):
        flash("Google連携がキャンセルされました。", "error")
        return redirect(url_for("profile.index"))

    state = request.args.get("state")
    expected_state = session.pop("google_oauth_state", None)
    if not state or state != expected_state:
        flash("Google連携の確認に失敗しました(もう一度お試しください)。", "error")
        return redirect(url_for("profile.index"))

    code = request.args.get("code")
    if not code:
        flash("Google連携に失敗しました。", "error")
        return redirect(url_for("profile.index"))

    try:
        token_res = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": Config.GOOGLE_CLIENT_ID,
                "client_secret": Config.GOOGLE_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": Config.GOOGLE_REDIRECT_URI,
            },
            timeout=10,
        )
        token_res.raise_for_status()
        access_token = token_res.json()["access_token"]

        user_res = requests.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        user_res.raise_for_status()
        profile = user_res.json()
    except Exception:
        flash("Googleとの通信に失敗しました。時間を置いてもう一度お試しください。", "error")
        return redirect(url_for("profile.index"))

    google_id = profile.get("sub")
    google_email = profile.get("email", "")

    if not google_id:
        flash("Googleのユーザー情報を取得できませんでした。", "error")
        return redirect(url_for("profile.index"))

    existing = User.query.filter_by(google_id=google_id).first()
    if existing and existing.id != current_user.id:
        flash("このGoogleアカウントは、すでに別のアカウントで連携済みです。", "error")
        return redirect(url_for("profile.index"))

    from models import utcnow, AdminAccountLog
    current_user.google_id = google_id
    current_user.google_email = google_email
    current_user.google_linked_at = utcnow()

    # 監査ログ: 誰が・いつ・どのメールアドレスで連携したかを記録する(全員分、管理画面で確認できる)
    db.session.add(AdminAccountLog(
        admin_username="system(Google連携)", action="google_linked", target_username=current_user.username,
        details=f"Googleアカウント: {google_email}",
    ))
    db.session.commit()

    flash(f"Googleアカウント「{google_email}」と連携しました!キャンペーンなどのお知らせがこちらのメールアドレスにも届くようになります。", "success")
    return redirect(url_for("profile.index"))


@google_auth_bp.route("/google/unlink", methods=["POST"])
@login_required
def google_unlink():
    current_user.google_id = None
    current_user.google_email = None
    current_user.google_linked_at = None
    db.session.commit()
    flash("Google連携を解除しました。", "success")
    return redirect(url_for("profile.index"))
