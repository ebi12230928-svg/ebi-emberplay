import hashlib
import secrets
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db


def utcnow():
    # SQLiteはDateTimeカラムを読み書きする際にtzinfoを保持しないため、
    # ここでは常にnaive(タイムゾーン情報なし)なUTC時刻で統一する。
    # (以前はtimezone-awareで返していたため、DBから読み戻した値と比較する際に
    #  「can't subtract offset-naive and offset-aware datetimes」で
    #  ウォレット画面がInternal Server Errorになることがあった)
    return datetime.utcnow()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    balance = db.Column(db.Integer, default=0, nullable=False)
    pending_rakeback = db.Column(db.Integer, default=0, nullable=False)

    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_vip = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    last_hourly_claim = db.Column(db.DateTime, nullable=True)
    last_daily_claim = db.Column(db.DateTime, nullable=True)
    last_weekly_claim = db.Column(db.DateTime, nullable=True)
    last_monthly_claim = db.Column(db.DateTime, nullable=True)
    last_reload_claim = db.Column(db.DateTime, nullable=True)
    login_streak_count = db.Column(db.Integer, default=0, nullable=False)
    last_streak_claim = db.Column(db.DateTime, nullable=True)

    # ── 借金機能 ──
    debt = db.Column(db.Integer, default=0, nullable=False)
    debt_started_at = db.Column(db.DateTime, nullable=True)

    # ── プロヴァブリーフェア用シード ──
    server_seed = db.Column(db.String(64), default=lambda: secrets.token_hex(32))
    client_seed = db.Column(db.String(64), default=lambda: secrets.token_hex(8))
    nonce = db.Column(db.Integer, default=0, nullable=False)

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    @property
    def server_seed_hash(self):
        return hashlib.sha256(self.server_seed.encode()).hexdigest()

    def rotate_server_seed(self):
        """現在のシードを公開し、新しいシードを生成する(検証用に古いシードを返す)"""
        old_seed = self.server_seed
        old_nonce = self.nonce
        self.server_seed = secrets.token_hex(32)
        self.nonce = 0
        return old_seed, old_nonce


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    amount = db.Column(db.Integer, nullable=False)  # 正=増加 / 負=減少
    kind = db.Column(db.String(32), nullable=False)  # admin_grant / daily / weekly / monthly / reload / rakeback / bet / payout
    description = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User", backref=db.backref("transactions", lazy="dynamic"))


class BetRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    game = db.Column(db.String(32), nullable=False)
    wager = db.Column(db.Integer, nullable=False)
    payout = db.Column(db.Integer, nullable=False)
    multiplier = db.Column(db.Float, nullable=False)
    server_seed_hash = db.Column(db.String(64), nullable=False)
    client_seed = db.Column(db.String(64), nullable=False)
    nonce = db.Column(db.Integer, nullable=False)
    result_json = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User", backref=db.backref("bets", lazy="dynamic"))


class MinesGame(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)

    wager = db.Column(db.Integer, nullable=False)
    grid_size = db.Column(db.Integer, default=25, nullable=False)
    mine_count = db.Column(db.Integer, nullable=False)

    mine_positions_json = db.Column(db.Text, nullable=False)  # JSON配列(内部用・終了まで非公開)
    revealed_json = db.Column(db.Text, default="[]")

    server_seed_hash = db.Column(db.String(64), nullable=False)
    client_seed = db.Column(db.String(64), nullable=False)
    nonce = db.Column(db.Integer, nullable=False)

    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User", backref=db.backref("active_mines_game", uselist=False))


class HiLoGame(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)

    wager = db.Column(db.Integer, nullable=False)
    current_rank = db.Column(db.Integer, nullable=False)   # 1(A)〜13(K)
    multiplier = db.Column(db.Float, default=1.0, nullable=False)
    rounds_played = db.Column(db.Integer, default=0, nullable=False)
    passes_used = db.Column(db.Integer, default=0, nullable=False)

    server_seed_hash = db.Column(db.String(64), nullable=False)
    client_seed = db.Column(db.String(64), nullable=False)
    nonce = db.Column(db.Integer, nullable=False)

    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User", backref=db.backref("active_hilo_game", uselist=False))


class TowerGame(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)

    wager = db.Column(db.Integer, nullable=False)
    difficulty = db.Column(db.String(16), nullable=False)
    tiles_per_row = db.Column(db.Integer, nullable=False)
    bad_per_row = db.Column(db.Integer, nullable=False)
    total_rows = db.Column(db.Integer, nullable=False)

    bad_positions_json = db.Column(db.Text, nullable=False)  # 各行の「悪いマス」インデックス配列のJSON
    current_row = db.Column(db.Integer, default=0, nullable=False)

    server_seed_hash = db.Column(db.String(64), nullable=False)
    client_seed = db.Column(db.String(64), nullable=False)
    nonce = db.Column(db.Integer, nullable=False)

    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User", backref=db.backref("active_tower_game", uselist=False))


class BlackjackGame(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)

    wager = db.Column(db.Integer, nullable=False)
    deck_json = db.Column(db.Text, nullable=False)      # 残りの山札(カードコードの配列)
    player_hand_json = db.Column(db.Text, nullable=False)
    dealer_hand_json = db.Column(db.Text, nullable=False)
    doubled = db.Column(db.Boolean, default=False, nullable=False)
    finished = db.Column(db.Boolean, default=False, nullable=False)

    server_seed_hash = db.Column(db.String(64), nullable=False)
    client_seed = db.Column(db.String(64), nullable=False)
    nonce = db.Column(db.Integer, nullable=False)

    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User", backref=db.backref("active_blackjack_game", uselist=False))


class CrashGame(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)

    wager = db.Column(db.Integer, nullable=False)
    crash_point = db.Column(db.Float, nullable=False)   # 内部用・確定済みだが終了まで非公開
    started_at = db.Column(db.DateTime, default=utcnow)

    server_seed_hash = db.Column(db.String(64), nullable=False)
    client_seed = db.Column(db.String(64), nullable=False)
    nonce = db.Column(db.Integer, nullable=False)

    user = db.relationship("User", backref=db.backref("active_crash_game", uselist=False))


class VideoPokerGame(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)

    wager = db.Column(db.Integer, nullable=False)
    hand_json = db.Column(db.Text, nullable=False)
    deck_json = db.Column(db.Text, nullable=False)

    server_seed_hash = db.Column(db.String(64), nullable=False)
    client_seed = db.Column(db.String(64), nullable=False)
    nonce = db.Column(db.Integer, nullable=False)

    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User", backref=db.backref("active_videopoker_game", uselist=False))


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    message = db.Column(db.String(500), nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User", backref=db.backref("notifications", lazy="dynamic"))


class RedeemCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False, index=True)
    amount = db.Column(db.Integer, nullable=False)

    # "once_per_user": 1人1回まで(何人でも利用可) / "global_limit": 全体で合計N回まで
    code_type = db.Column(db.String(20), nullable=False, default="once_per_user")
    max_global_uses = db.Column(db.Integer, nullable=True)
    total_uses = db.Column(db.Integer, default=0, nullable=False)

    active = db.Column(db.Boolean, default=True, nullable=False)
    created_by = db.Column(db.String(32), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)


class RedeemCodeRedemption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code_id = db.Column(db.Integer, db.ForeignKey("redeem_code.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    redeemed_at = db.Column(db.DateTime, default=utcnow)

    code = db.relationship("RedeemCode", backref=db.backref("redemptions", lazy="dynamic"))
    user = db.relationship("User", backref=db.backref("code_redemptions", lazy="dynamic"))


class AppState(db.Model):
    """簡易的なキーバリューストア(スポーツデータの最終同期時刻などを保存する)"""
    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.String(256))


class SportsEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    sport = db.Column(db.String(32), default="soccer")
    league_name = db.Column(db.String(128))
    home_team = db.Column(db.String(128))
    away_team = db.Column(db.String(128))
    event_time = db.Column(db.DateTime, nullable=True)

    status = db.Column(db.String(16), default="upcoming")  # upcoming / finished
    home_score = db.Column(db.Integer, nullable=True)
    away_score = db.Column(db.Integer, nullable=True)
    winner = db.Column(db.String(16), nullable=True)  # home / away / draw

    odds_home = db.Column(db.Float, default=1.9)
    odds_draw = db.Column(db.Float, default=3.2)
    odds_away = db.Column(db.Float, default=1.9)

    created_at = db.Column(db.DateTime, default=utcnow)


class SportsBet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    event_id = db.Column(db.Integer, db.ForeignKey("sports_event.id"), nullable=False, index=True)

    pick = db.Column(db.String(16), nullable=False)  # home / draw / away
    wager = db.Column(db.Integer, nullable=False)
    odds = db.Column(db.Float, nullable=False)  # 賭けた時点のオッズを固定で記録
    status = db.Column(db.String(16), default="pending")  # pending / won / lost
    payout = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User", backref=db.backref("sports_bets", lazy="dynamic"))
    event = db.relationship("SportsEvent", backref=db.backref("bets", lazy="dynamic"))


class VipAnnouncement(db.Model):
    """VIPラウンジ内の、管理者だけが書き込めるお知らせ欄"""
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.String(32), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)


class Announcement(db.Model):
    """全プレイヤーに公開される、管理者だけが書き込めるお知らせ掲示板"""
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.String(32), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)


class ChatMessage(db.Model):
    """全プレイヤー参加のチャット(ポーリング方式)"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    message = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User", backref=db.backref("chat_messages", lazy="dynamic"))


class WarGame(db.Model):
    """War(引き分け時の「戦争に行く/降参」待ち状態)を保持するモデル"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)

    total_wager = db.Column(db.Integer, nullable=False)  # ここまでに賭けた合計(warするたび倍になる)
    player_rank = db.Column(db.Integer, nullable=False)
    dealer_rank = db.Column(db.Integer, nullable=False)

    server_seed_hash = db.Column(db.String(64), nullable=False)
    client_seed = db.Column(db.String(64), nullable=False)
    nonce = db.Column(db.Integer, nullable=False)

    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User", backref=db.backref("active_war_game", uselist=False))


class CrapsGame(db.Model):
    """Craps(Pass/Don't Pass)の「ポイント」確定後の進行状態を保持するモデル"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)

    bet_type = db.Column(db.String(16), nullable=False)  # pass / dont_pass
    wager = db.Column(db.Integer, nullable=False)
    point = db.Column(db.Integer, nullable=False)

    server_seed_hash = db.Column(db.String(64), nullable=False)
    client_seed = db.Column(db.String(64), nullable=False)
    nonce = db.Column(db.Integer, nullable=False)

    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User", backref=db.backref("active_craps_game", uselist=False))


class ThreeCardPokerGame(db.Model):
    """Three Card Pokerの、Play/Fold選択待ちの状態を保持するモデル"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)

    ante = db.Column(db.Integer, nullable=False)
    player_hand_json = db.Column(db.Text, nullable=False)
    dealer_hand_json = db.Column(db.Text, nullable=False)

    server_seed_hash = db.Column(db.String(64), nullable=False)
    client_seed = db.Column(db.String(64), nullable=False)
    nonce = db.Column(db.Integer, nullable=False)

    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User", backref=db.backref("active_threecard_game", uselist=False))
