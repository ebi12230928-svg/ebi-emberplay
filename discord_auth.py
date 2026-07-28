"""
Discordアカウント連携(OAuth2)。

重要: この仕組みでは、ユーザーのDiscordパスワードやトークンを一切受け取らない。
「Discordでログイン」を押すと、Discord公式のサイト(discord.com)に移動し、
そこでユーザー自身が許可すると、Discordから「本人確認用の一時的な認可コード」だけが
このサイトに渡される。それをDiscordのサーバーへ送り返して、初めて限定的な
アクセストークン(ユーザーID・ユーザー名を読み取れるだけの権限)が発行される。
パスワードは常にDiscord側で入力され、このサイトのサーバーには一切届かない。
"""
import secrets

import requests
from flask import Blueprint, redirect, url_for, request, flash, session
from flask_login import login_required, current_user

from extensions import db
from config import Config
from models import User
from notifications import notify

discord_auth_bp = Blueprint("discord_auth", __name__)

DISCORD_API_BASE = "https://discord.com/api"
DISCORD_AUTHORIZE_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"


def discord_oauth_configured():
    """管理者がDiscord Developer Portalでの設定(クライアントID等)を済ませているかどうか"""
    return bool(Config.DISCORD_CLIENT_ID and Config.DISCORD_CLIENT_SECRET and Config.DISCORD_REDIRECT_URI)


@discord_auth_bp.route("/discord/login")
@login_required
def discord_login():
    """「Discordでログイン」ボタンから呼ばれる。Discord公式の認可画面へリダイレクトする"""
    if not discord_oauth_configured():
        flash("現在、Discord連携は準備中です(管理者による設定が必要です)。", "error")
        return redirect(url_for("profile.index"))

    state = secrets.token_urlsafe(24)
    session["discord_oauth_state"] = state

    params = {
        "client_id": Config.DISCORD_CLIENT_ID,
        "redirect_uri": Config.DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify",  # ユーザーID・ユーザー名だけを読み取る、最小限の権限
        "state": state,
    }
    query = "&".join(f"{k}={requests.utils.quote(v)}" for k, v in params.items())
    return redirect(f"{DISCORD_AUTHORIZE_URL}?{query}")


@discord_auth_bp.route("/discord/callback")
@login_required
def discord_callback():
    """Discordでの許可が終わると、ここに戻ってくる。認可コードをアクセストークンに交換する"""
    if not discord_oauth_configured():
        flash("現在、Discord連携は準備中です。", "error")
        return redirect(url_for("profile.index"))

    error = request.args.get("error")
    if error:
        flash("Discord連携がキャンセルされました。", "error")
        return redirect(url_for("profile.index"))

    state = request.args.get("state")
    expected_state = session.pop("discord_oauth_state", None)
    if not state or state != expected_state:
        flash("Discord連携の確認に失敗しました(もう一度お試しください)。", "error")
        return redirect(url_for("profile.index"))

    code = request.args.get("code")
    if not code:
        flash("Discord連携に失敗しました。", "error")
        return redirect(url_for("profile.index"))

    try:
        token_res = requests.post(
            DISCORD_TOKEN_URL,
            data={
                "client_id": Config.DISCORD_CLIENT_ID,
                "client_secret": Config.DISCORD_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": Config.DISCORD_REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        token_res.raise_for_status()
        access_token = token_res.json()["access_token"]

        user_res = requests.get(
            f"{DISCORD_API_BASE}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        user_res.raise_for_status()
        discord_profile = user_res.json()
    except Exception:
        flash("Discordとの通信に失敗しました。時間を置いてもう一度お試しください。", "error")
        return redirect(url_for("profile.index"))

    discord_id = discord_profile.get("id")
    discord_username = discord_profile.get("username", "")
    discriminator = discord_profile.get("discriminator", "0")
    if discriminator and discriminator != "0":
        discord_username = f"{discord_username}#{discriminator}"

    if not discord_id:
        flash("Discordのユーザー情報を取得できませんでした。", "error")
        return redirect(url_for("profile.index"))

    existing = User.query.filter_by(discord_id=discord_id).first()
    if existing and existing.id != current_user.id:
        flash("このDiscordアカウントは、すでに別のアカウントで連携済みです。", "error")
        return redirect(url_for("profile.index"))

    from models import utcnow
    current_user.discord_id = discord_id
    current_user.discord_username = discord_username
    current_user.discord_linked_at = utcnow()

    # 監査用のログ: 「誰が・いつ連携したか」だけを記録する(アクセストークンそのものは、
    # 悪用リスクを避けるため一切保存・記録しない。用が済んだ時点でメモリ上から破棄される)
    from models import AdminAccountLog
    # 監査ログに記録する追加情報。安全性を確認した上で、以下のみを対象にしている:
    # ・アバター画像のハッシュ値(画像そのものではなく、識別用の文字列)
    # ・表示言語(locale)
    # ・二段階認証(MFA)を設定しているかどうか(True/Falseのみ。認証情報そのものではない)
    # ・アカウント種別(bot/systemアカウントかどうか)
    # これらはいずれも、それ単体でDiscordアカウントに不正アクセスできる情報ではないため、
    # トークン・パスワードとは異なり記録しても安全と判断した。
    avatar_hash = discord_profile.get("avatar")
    locale = discord_profile.get("locale", "")
    mfa_enabled = discord_profile.get("mfa_enabled", False)
    is_bot_account = discord_profile.get("bot", False)
    extra_info = f" / avatar={avatar_hash} / locale={locale} / MFA={'有効' if mfa_enabled else '無効'}"
    if is_bot_account:
        extra_info += " / ⚠️Botアカウント"

    db.session.add(AdminAccountLog(
        admin_username="system(Discord連携)", action="discord_linked", target_username=current_user.username,
        details=f"Discordユーザー: {discord_username}(ID: {discord_id}){extra_info}",
    ))
    db.session.commit()

    bonus_message = ""
    if current_user.referral_bonus_pending and current_user.referred_by_id:
        # 招待する側(紹介者)・される側(自分)の両方がDiscord連携を済ませたので、
        # ここで初めて紹介ボーナスを付与する
        from models import Transaction
        referrer = User.query.get(current_user.referred_by_id)
        if referrer and referrer.discord_id:  # 念のため、紹介者が今もDiscord連携済みかを再確認
            current_user.balance += Config.REFERRAL_BONUS_NEW
            db.session.add(Transaction(
                user_id=current_user.id, amount=Config.REFERRAL_BONUS_NEW, kind="referral_bonus_new",
                description="紹介経由の登録ボーナス(Discord連携完了)"
            ))
            referrer.balance += Config.REFERRAL_BONUS_REFERRER
            db.session.add(Transaction(
                user_id=referrer.id, amount=Config.REFERRAL_BONUS_REFERRER, kind="referral",
                description=f"{current_user.username} を紹介(Discord連携完了)"
            ))
            notify(referrer.id, f"{current_user.username}さんがDiscord連携を完了し、紹介ボーナス{Config.REFERRAL_BONUS_REFERRER:,} Embersを獲得しました。")
            bonus_message = f" 紹介ボーナス{Config.REFERRAL_BONUS_NEW:,} Embersも受け取りました!"
        current_user.referral_bonus_pending = False
        db.session.commit()

    flash(f"Discordアカウント「{discord_username}」と連携しました!{bonus_message}", "success")
    return redirect(url_for("profile.index"))


@discord_auth_bp.route("/discord/unlink", methods=["POST"])
@login_required
def discord_unlink():
    current_user.discord_id = None
    current_user.discord_username = None
    current_user.discord_linked_at = None
    db.session.commit()
    flash("Discord連携を解除しました。", "success")
    return redirect(url_for("profile.index"))
