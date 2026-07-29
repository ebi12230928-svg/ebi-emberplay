"""
不正検知(CAPTCHA連続失敗・動画視聴収益の異常なペース・IPの多重アカウント・VPN/プロキシなど)から、
自動でブラックリストに追加する機能。各所から check_and_flag(user_id, reason, details) を
呼ぶだけで、記録 → 直近の回数チェック → 閾値を超えたら自動ブラックリスト、まで一括で行う。
"""
from datetime import timedelta

from flask import request
from extensions import db
from models import User, SuspiciousActivityLog, AdminAccountLog, IpAccessLog, utcnow
from notifications import notify_all

# 不正の種類ごとに、「何分以内に何回で自動ブラックリストにするか」を設定する
FLAG_RULES = {
    "captcha_fail_register": {"window_minutes": 10, "threshold": 8},
    "captcha_fail_upload": {"window_minutes": 10, "threshold": 8},
    "captcha_fail_watch": {"window_minutes": 10, "threshold": 8},
    "watch_progress_abuse": {"window_minutes": 10, "threshold": 5},
    "referral_burst": {"window_minutes": 60, "threshold": 3},        # 短時間に大量の招待を繰り返す
    "withdrawal_spam": {"window_minutes": 60, "threshold": 5},        # 出金申請の連発
    "multi_account_same_ip": {"window_minutes": 1440, "threshold": 1},  # 同じIPからの多重アカウントは即座に対象
    "vpn_detected": {"window_minutes": 1440, "threshold": 1},          # VPN/プロキシ検知は1回で即対象
}

# 管理画面で表示する、理由コードの日本語ラベル(「なぜブラックリストに入ったか」を分かりやすくするため)
REASON_LABELS = {
    "captcha_fail_register": "新規登録時のCAPTCHA連続失敗",
    "captcha_fail_upload": "動画アップロード時のCAPTCHA連続失敗",
    "captcha_fail_watch": "動画視聴時のCAPTCHA連続失敗",
    "watch_progress_abuse": "動画視聴報告の異常な頻度(自動化ツールの疑い)",
    "referral_burst": "短時間での招待の急増(自作自演の疑い)",
    "withdrawal_spam": "出金申請の連発",
    "multi_account_same_ip": "同一IPアドレスからの多重アカウント",
    "vpn_detected": "VPN/データセンター経由の疑いがあるアクセス",
}


def _client_ip():
    """
    実際のアクセス元IPを取得する。PythonAnywhereなどリバースプロキシ経由の環境では、
    X-Forwarded-Forヘッダーの一番左側(最初にアクセスしてきた相手)を優先的に使う。
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


# VPN・データセンター経由でよく使われる代表的なIPレンジ(一部)。
# 本格的なVPN検知には、IPQualityScoreやIP2Proxyなどの有料IP判定サービスとの連携が必要になる。
# ここでは、外部サービスとの契約が無くても最低限の判定ができるよう、
# 主要クラウド事業者のIPレンジ(VPN業者がよく間借りしている)を簡易的にチェックしている。
#
# 【重要な限界】この方式では、NordVPN・ExpressVPN・Surfsharkなど、一般的な民生用VPNサービスの
# 多くは検知できない。これらの多くは、クラウド事業者だけでなく、独自に確保した多種多様なIPを
# 使っており、住宅用回線のIPに偽装するサービス(レジデンシャルIP)も増えているため、
# IPレンジの一覧だけでは検知しきれない。本当に確実な検知が必要な場合は、
# 有料のIP判定サービス(下記のcheck_via_external_api関数を参照)との連携が必須になる。
_KNOWN_DATACENTER_PREFIXES = (
    "3.", "13.", "18.", "34.", "35.", "52.", "54.",   # AWS系
    "104.196.", "104.197.", "104.198.", "35.184.", "35.185.",  # Google Cloud系
    "20.", "40.", "52.16", "104.40.",                  # Azure系
    "104.131.", "138.68.", "142.93.", "159.65.", "165.22.",  # DigitalOcean系
    "45.32.", "45.63.", "45.76.", "45.77.", "108.61.",  # Vultr系
    "172.104.", "172.105.", "139.162.", "139.144.",     # Linode(Akamai)系
    "185.220.", "185.221.",                              # よく知られたVPN/Tor系ホスティングブロック
    "5.157.", "23.129.", "51.15.", "51.68.", "51.75.", "51.77.", "51.83.", "51.89.",  # 欧州系VPS事業者に多い
)


def check_via_external_api(ip):
    """
    【差し替え用のフック】より確実なVPN判定をしたい場合は、この関数の中身を、
    IPQualityScore・IP2Proxy・IPHubなどの有料IP判定サービスへのAPI呼び出しに置き換えてください。
    (PythonAnywhereの無料プランでは、許可リストに無いドメインへは通信できないため、
    使うサービスのドメインを事前にPythonAnywhereサポートへ申請して許可してもらうか、
    有料プランへのアップグレードが必要になる場合があります)
    現時点では未設定のため、常にNoneを返す(=判定に使わない)。
    """
    return None


def is_vpn_or_proxy(ip):
    """
    VPN/プロキシ判定。まず外部API判定フック(設定されていれば)を試し、
    未設定の場合は、既知のデータセンター系IPレンジによる簡易判定にフォールバックする。
    あくまで「クラウド・データセンター経由の疑いがあるIPかどうか」の大まかな目安であり、
    完全な判定ではない(詳しくはcheck_via_external_apiのコメントを参照)。
    """
    if not ip or ip == "unknown":
        return False

    external_result = check_via_external_api(ip)
    if external_result is not None:
        return external_result

    return any(ip.startswith(prefix) for prefix in _KNOWN_DATACENTER_PREFIXES)


def track_anonymous_ip(ip, path=""):
    """
    ログインしていない訪問者のIPを記録する(ログイン済みユーザーとは別のテーブルに残す)。
    直近30分以内に同じIPの記録があれば、ログが埋め尽くされないよう新しい行は追加しない。
    """
    from datetime import timedelta
    from models import AnonymousIpLog

    if not ip or ip == "unknown":
        return

    cutoff = utcnow() - timedelta(minutes=30)
    recent = AnonymousIpLog.query.filter(
        AnonymousIpLog.ip_address == ip, AnonymousIpLog.created_at >= cutoff
    ).first()
    if recent:
        return  # 直近30分以内に同じIPの記録が既にあるので、追加しない

    db.session.add(AnonymousIpLog(ip_address=ip, path=path, vpn_flagged=is_vpn_or_proxy(ip)))
    db.session.commit()


def track_login_ip(user):
    """
    ログインが成功した瞬間に呼ぶ。前回と同じIPであっても、必ず1件記録する
    (「いつ・どのIPでログインしたか」を漏れなく確認できるようにするため)。
    auth.pyのlogin()から呼ばれる。
    """
    ip = _client_ip()
    if not ip or ip == "unknown":
        return

    if not user.signup_ip:
        user.signup_ip = ip
    user.last_ip = ip
    user.last_ip_seen_at = utcnow()

    db.session.add(IpAccessLog(user_id=user.id, ip_address=ip, vpn_flagged=is_vpn_or_proxy(ip), event_type="login"))
    db.session.commit()

    if is_vpn_or_proxy(ip) and not user.vpn_flagged:
        user.vpn_flagged = True
        db.session.commit()
        check_and_flag(user.id, "vpn_detected", f"データセンター/VPN経由の疑いがあるIP({ip})からのログイン")


def track_ip(user):
    """
    ログイン中のユーザーのアクセスIPを記録し、多重アカウント(同じIPから複数アカウント作成)や
    VPN/プロキシの疑いを検知する。app.pyのbefore_requestから毎リクエスト呼ばれる。
    IPアドレスの履歴は、前回と異なるIPになった時だけ新しい行として記録する
    (毎リクエスト記録すると、ログがすぐに膨大な量になってしまうため。
    ログイン時は、track_login_ipで別途必ず記録される)。
    """
    ip = _client_ip()
    if not ip or ip == "unknown":
        return

    ip_changed = user.last_ip != ip

    if not user.signup_ip:
        user.signup_ip = ip
    user.last_ip = ip
    user.last_ip_seen_at = utcnow()
    db.session.commit()

    if ip_changed:
        db.session.add(IpAccessLog(user_id=user.id, ip_address=ip, vpn_flagged=is_vpn_or_proxy(ip), event_type="ip_changed"))
        db.session.commit()

    # 同じIPを使っている、自分以外のアカウントがどれだけあるかを確認する
    other_accounts_same_ip = User.query.filter(
        User.id != user.id, User.last_ip == ip, User.is_npc.is_(False)
    ).count()
    if other_accounts_same_ip >= 1:  # 同じIPを使う他のアカウントが1つでもあれば、即座に検知する
        check_and_flag(user.id, "multi_account_same_ip", f"同一IP({ip})を使う他アカウントが{other_accounts_same_ip}件")

    if is_vpn_or_proxy(ip) and not user.vpn_flagged:
        user.vpn_flagged = True
        db.session.commit()
        check_and_flag(user.id, "vpn_detected", f"データセンター/VPN経由の疑いがあるIP({ip})からのアクセス")


def check_and_flag(user_id, reason, details=""):
    """
    不正の疑いがある行動を1件記録し、直近の同種のフラグ回数が閾値を超えていたら、
    自動的にそのユーザーをブラックリストに追加する。
    戻り値: 今回の記録によって新たにブラックリスト入りした場合はTrue、それ以外はFalse。
    """
    if not user_id:
        return False

    db.session.add(SuspiciousActivityLog(user_id=user_id, reason=reason, details=details))
    db.session.commit()

    rule = FLAG_RULES.get(reason)
    if not rule:
        return False

    cutoff = utcnow() - timedelta(minutes=rule["window_minutes"])
    recent_count = SuspiciousActivityLog.query.filter(
        SuspiciousActivityLog.user_id == user_id,
        SuspiciousActivityLog.reason == reason,
        SuspiciousActivityLog.created_at >= cutoff,
    ).count()

    if recent_count < rule["threshold"]:
        return False

    user = User.query.get(user_id)
    if not user or user.is_blacklisted or user.is_admin:
        return False  # 既にブラックリスト済み、または管理者は対象外にする

    user.is_blacklisted = True
    reason_label = REASON_LABELS.get(reason, reason)
    db.session.add(AdminAccountLog(
        admin_username="system(自動検知)", action="auto_blacklisted", target_username=user.username,
        details=f"理由: {reason_label} / 直近{rule['window_minutes']}分で{recent_count}回検知(最後の検知内容: {details})",
    ))
    db.session.commit()

    notify_all(f"⚠️ 不正の疑い({reason_label})により、{user.username} を自動的にブラックリストに追加しました。管理画面から確認できます。")
    db.session.commit()
    return True
