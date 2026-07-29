"""
パスキー(WebAuthn)によるログイン機能。指紋認証・顔認証などで、パスワード無しでログインできる。

重要: 指紋・顔の生体情報そのものは、常に端末(スマホ・PC)側にのみ保存され、
このサイトのサーバーには一切送られてこない。サーバー側が保存するのは「公開鍵」だけで、
これは仮に漏れても、それだけでは他人になりすましてログインすることはできない。

登録(パスキーを追加する)の流れ:
1. ブラウザから /passkey/register/options を呼び、サーバーが「今回限りのチャレンジ」を発行する
2. ブラウザが navigator.credentials.create() を呼び、端末の生体認証で「鍵ペア」を作る
3. 出来た公開鍵を /passkey/register/verify に送り、サーバー側で検証・保存する

ログインの流れ:
1. ブラウザから /passkey/login/options を呼び、サーバーが「今回限りのチャレンジ」を発行する
2. ブラウザが navigator.credentials.get() を呼び、端末の生体認証で電子署名を作る
3. その署名を /passkey/login/verify に送り、サーバー側で保存済みの公開鍵と照合し、
   一致すればログインさせる
"""
import base64

from flask import Blueprint, request, jsonify, session, url_for
from flask_login import login_required, current_user, login_user

from extensions import db
from config import Config
from models import User, PasskeyCredential

webauthn_bp = Blueprint("webauthn", __name__)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def webauthn_configured():
    return bool(Config.WEBAUTHN_RP_ID)


@webauthn_bp.route("/passkey/register/options", methods=["POST"])
@login_required
def register_options():
    """パスキー登録用の「チャレンジ」を発行する"""
    try:
        from webauthn import generate_registration_options, options_to_json
        from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement
    except ImportError:
        return jsonify({"error": "パスキー機能がまだ準備できていません。"}), 503

    existing_credentials = PasskeyCredential.query.filter_by(user_id=current_user.id).all()
    exclude = [
        PublicKeyCredentialDescriptor(id=base64.urlsafe_b64decode(c.credential_id + "=="))
        for c in existing_credentials
    ]

    options = generate_registration_options(
        rp_id=Config.WEBAUTHN_RP_ID,
        rp_name=Config.WEBAUTHN_RP_NAME,
        user_id=str(current_user.id).encode(),
        user_name=current_user.username,
        user_display_name=current_user.username,
        exclude_credentials=exclude,
    )
    session["passkey_reg_challenge"] = _b64url_encode(options.challenge)
    return options_to_json(options), 200, {"Content-Type": "application/json"}


@webauthn_bp.route("/passkey/register/verify", methods=["POST"])
@login_required
def register_verify():
    """ブラウザから届いた公開鍵を検証し、保存する"""
    try:
        from webauthn import verify_registration_response
        from webauthn.helpers.structs import RegistrationCredential
    except ImportError:
        return jsonify({"ok": False}), 503

    challenge = session.pop("passkey_reg_challenge", None)
    if not challenge:
        return jsonify({"ok": False, "error": "確認の有効期限が切れました。もう一度お試しください。"}), 400

    try:
        credential = RegistrationCredential.parse_raw(request.get_data())
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=base64.urlsafe_b64decode(challenge + "=="),
            expected_rp_id=Config.WEBAUTHN_RP_ID,
            expected_origin=Config.WEBAUTHN_ORIGIN,
        )
    except Exception as e:
        return jsonify({"ok": False, "error": "パスキーの登録に失敗しました。"}), 400

    device_label = request.args.get("label", "この端末")
    db.session.add(PasskeyCredential(
        user_id=current_user.id,
        credential_id=_b64url_encode(verification.credential_id),
        public_key=_b64url_encode(verification.credential_public_key),
        sign_count=verification.sign_count,
        device_label=device_label,
    ))
    db.session.commit()
    return jsonify({"ok": True})


@webauthn_bp.route("/passkey/login/options", methods=["POST"])
def login_options():
    """パスキーでログインする際の「チャレンジ」を発行する(まだログインしていない状態で呼ばれる)"""
    try:
        from webauthn import generate_authentication_options, options_to_json
    except ImportError:
        return jsonify({"error": "パスキー機能がまだ準備できていません。"}), 503

    options = generate_authentication_options(rp_id=Config.WEBAUTHN_RP_ID)
    session["passkey_login_challenge"] = _b64url_encode(options.challenge)
    return options_to_json(options), 200, {"Content-Type": "application/json"}


@webauthn_bp.route("/passkey/login/verify", methods=["POST"])
def login_verify():
    """ブラウザから届いた電子署名を検証し、一致すればログインさせる"""
    try:
        from webauthn import verify_authentication_response
        from webauthn.helpers.structs import AuthenticationCredential
    except ImportError:
        return jsonify({"ok": False}), 503

    challenge = session.pop("passkey_login_challenge", None)
    if not challenge:
        return jsonify({"ok": False, "error": "確認の有効期限が切れました。もう一度お試しください。"}), 400

    try:
        credential = AuthenticationCredential.parse_raw(request.get_data())
        credential_id = _b64url_encode(credential.raw_id)
    except Exception:
        return jsonify({"ok": False, "error": "パスキーの読み取りに失敗しました。"}), 400

    stored = PasskeyCredential.query.filter_by(credential_id=credential_id).first()
    if not stored:
        return jsonify({"ok": False, "error": "登録されていないパスキーです。"}), 400

    try:
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=base64.urlsafe_b64decode(challenge + "=="),
            expected_rp_id=Config.WEBAUTHN_RP_ID,
            expected_origin=Config.WEBAUTHN_ORIGIN,
            credential_public_key=base64.urlsafe_b64decode(stored.public_key + "=="),
            credential_current_sign_count=stored.sign_count,
        )
    except Exception:
        return jsonify({"ok": False, "error": "パスキーの検証に失敗しました。"}), 400

    from models import utcnow
    stored.sign_count = verification.new_sign_count
    stored.last_used_at = utcnow()
    db.session.commit()

    user = User.query.get(stored.user_id)
    if not user:
        return jsonify({"ok": False}), 400

    login_user(user, remember=True)  # パスキーでログインした場合は、常に長期間ログイン状態を保持する

    try:
        from fraud_detection import track_login_ip
        track_login_ip(user)
    except Exception:
        pass

    return jsonify({"ok": True, "redirect": url_for("lobby.index")})


@webauthn_bp.route("/passkey/list")
@login_required
def list_passkeys():
    credentials = PasskeyCredential.query.filter_by(user_id=current_user.id).all()
    return jsonify([
        {"id": c.id, "device_label": c.device_label, "created_at": c.created_at.isoformat()}
        for c in credentials
    ])


@webauthn_bp.route("/passkey/<int:credential_id>/delete", methods=["POST"])
@login_required
def delete_passkey(credential_id):
    cred = PasskeyCredential.query.filter_by(id=credential_id, user_id=current_user.id).first()
    if cred:
        db.session.delete(cred)
        db.session.commit()
    return jsonify({"ok": True})
