"""
動画投稿・視聴プラットフォーム。
- 動画は15分以内のもののみアップロード可能(ffprobeで長さを検証する。ffprobeが使えない環境では
  検証をスキップし、そのままアップロードを許可する)
- 視聴1分につき0.1円(=100 milliyen)の収益が発生する。ただし同じ動画を何度見ても、
  1動画につき収益として計上されるのは最大30分(1800秒)まで(不正な収益稼ぎ対策)
- 収益はEmbers(サイト内ポイント)とは別の「実際の円建て収益」として管理し、
  500円以上貯まったら出金申請できる。出金申請時にPayPayのID(電話番号など)または
  請求リンクのどちらかを入力してもらい、管理者が手動で実際に送金した後、
  管理画面から「送金済み」ボタンを押して完了とする。このサイト自体が自動で送金することは一切ない。
"""
import os
import subprocess
import uuid

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, send_from_directory, session
from flask_login import login_required, current_user

from extensions import db
from models import User, Video, VideoComment, VideoLike, ChannelSubscription, VideoWatchProgress, WithdrawalRequest, WithdrawalPoolSetting
from notifications import notify
from auth import _generate_captcha

videos_bp = Blueprint("videos", __name__)

MAX_VIDEO_DURATION_SECONDS = 15 * 60          # 動画は15分以内のみアップロード可能
EARNINGS_MILLIYEN_PER_MINUTE = 10              # 1分視聴につき0.01円(=10 milliyen。1000 milliyen = 1円)
MIN_WITHDRAWAL_YEN = 500                       # 最低出金額
ALLOWED_VIDEO_EXTENSIONS = {"mp4", "webm", "mov", "m4v"}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024           # 500MB(PythonAnywhereのディスク容量に配慮した上限)


def _upload_dir():
    upload_dir = os.path.join(current_app.root_path, "static", "uploads", "videos")
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def _probe_duration_seconds(filepath):
    """
    ffprobeで動画の長さ(秒)を取得する。ffprobeが使えない環境(PythonAnywhereの無料プランなど)では
    Noneを返し、呼び出し側で「検証をスキップして許可する」扱いにする。
    """
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", filepath],
            capture_output=True, text=True, timeout=30,
        )
        return int(float(result.stdout.strip()))
    except Exception:
        return None


def _remaining_withdrawal_budget():
    """
    管理者が設定した出金予算の上限から、これまでの申請額(確認待ち+送金済みの両方)を
    差し引いた「残り出金可能額」を計算する。管理者が予算を設定していない場合はNone(無制限)を返す。
    """
    pool = WithdrawalPoolSetting.query.get("default")
    if not pool or pool.total_budget_yen <= 0:
        return None
    reserved = db.session.query(db.func.coalesce(db.func.sum(WithdrawalRequest.amount_yen), 0)).filter(
        WithdrawalRequest.status.in_(["pending", "sent"])
    ).scalar()
    return max(0, pool.total_budget_yen - reserved)


@videos_bp.route("/videos")
@login_required
def index():
    videos = Video.query.order_by(Video.created_at.desc()).limit(60).all()
    return render_template("videos_index.html", videos=videos)


@videos_bp.route("/videos/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "GET":
        target, options = _generate_captcha("captcha_video_upload")
        return render_template(
            "videos_upload.html", max_minutes=MAX_VIDEO_DURATION_SECONDS // 60,
            max_mb=MAX_UPLOAD_BYTES // (1024 * 1024),
            captcha_target=target, captcha_options=options,
        )

    captcha_answer = request.form.get("captcha_answer", "").strip()
    correct_answer = session.pop("captcha_video_upload", None)
    if not correct_answer or captcha_answer != correct_answer:
        flash("画像の確認に失敗しました。表示されたローマ字と一致するものを選び直してください。", "error")
        return redirect(url_for("videos.upload"))

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    file = request.files.get("video_file")

    if not title:
        flash("タイトルを入力してください。", "error")
        return redirect(url_for("videos.upload"))
    if not file or not file.filename:
        flash("動画ファイルを選択してください。", "error")
        return redirect(url_for("videos.upload"))

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        flash(f"対応していない形式です({', '.join(ALLOWED_VIDEO_EXTENSIONS)}のいずれかにしてください)。", "error")
        return redirect(url_for("videos.upload"))

    saved_filename = f"{uuid.uuid4().hex}.{ext}"
    saved_path = os.path.join(_upload_dir(), saved_filename)
    file.save(saved_path)

    file_size = os.path.getsize(saved_path)
    if file_size > MAX_UPLOAD_BYTES:
        os.remove(saved_path)
        flash(f"ファイルサイズが大きすぎます(上限{MAX_UPLOAD_BYTES // (1024*1024)}MB)。", "error")
        return redirect(url_for("videos.upload"))

    duration = _probe_duration_seconds(saved_path)
    if duration is not None and duration > MAX_VIDEO_DURATION_SECONDS:
        os.remove(saved_path)
        flash(f"動画は{MAX_VIDEO_DURATION_SECONDS // 60}分以内のものだけアップロードできます(この動画は約{duration // 60}分でした)。", "error")
        return redirect(url_for("videos.upload"))

    video = Video(
        uploader_id=current_user.id, title=title, description=description,
        filename=saved_filename, duration_seconds=duration or 0,
    )
    db.session.add(video)
    db.session.commit()

    flash("動画をアップロードしました!", "success")
    return redirect(url_for("videos.watch", video_id=video.id))


@videos_bp.route("/videos/file/<path:filename>")
@login_required
def serve_video_file(filename):
    return send_from_directory(_upload_dir(), filename)


@videos_bp.route("/videos/<int:video_id>")
@login_required
def watch(video_id):
    video = Video.query.get_or_404(video_id)
    video.view_count += 1
    db.session.commit()

    captcha_target, captcha_options = _generate_captcha(f"captcha_watch_{video_id}")

    comments = video.comments.order_by(VideoComment.created_at.desc()).all()
    my_like = VideoLike.query.filter_by(video_id=video_id, user_id=current_user.id).first()
    is_subscribed = ChannelSubscription.query.filter_by(
        subscriber_id=current_user.id, channel_owner_id=video.uploader_id
    ).first() is not None
    subscriber_count = ChannelSubscription.query.filter_by(channel_owner_id=video.uploader_id).count()

    return render_template(
        "videos_watch.html", video=video, comments=comments, my_like=my_like,
        is_subscribed=is_subscribed, subscriber_count=subscriber_count,
        captcha_target=captcha_target, captcha_options=captcha_options,
    )


WATCH_VERIFICATION_VALID_SECONDS = 10 * 60  # 一度確認したら10分間は再確認不要にする


@videos_bp.route("/videos/<int:video_id>/verify-watch", methods=["POST"])
@login_required
def verify_watch(video_id):
    """
    動画視聴による収益稼ぎを自動化ツールで行えないようにするための本人確認。
    正解すると、このセッションでこの動画については10分間、視聴収益のカウントが有効になる。
    10分経つと再度確認が必要になる(スクリプトを流しっぱなしにして稼ぎ続けることを防ぐため)。
    """
    from models import utcnow
    from datetime import timedelta

    Video.query.get_or_404(video_id)
    data = request.get_json(force=True)
    answer = (data.get("answer") or "").strip()

    correct_answer = session.pop(f"captcha_watch_{video_id}", None)
    if not correct_answer or answer != correct_answer:
        target, options = _generate_captcha(f"captcha_watch_{video_id}")
        return jsonify({"ok": False, "captcha_target": target, "captcha_options": options}), 400

    expiry = utcnow() + timedelta(seconds=WATCH_VERIFICATION_VALID_SECONDS)
    session[f"watch_verified_{video_id}"] = expiry.isoformat()
    return jsonify({"ok": True, "valid_seconds": WATCH_VERIFICATION_VALID_SECONDS})


@videos_bp.route("/videos/<int:video_id>/watch-captcha")
@login_required
def watch_captcha(video_id):
    """再確認が必要になった時に、新しいお手本・選択肢を取得するためのAPI"""
    Video.query.get_or_404(video_id)
    target, options = _generate_captcha(f"captcha_watch_{video_id}")
    return jsonify({"captcha_target": target, "captcha_options": options})


@videos_bp.route("/videos/<int:video_id>/comment", methods=["POST"])
@login_required
def comment(video_id):
    video = Video.query.get_or_404(video_id)
    message = request.form.get("message", "").strip()
    if not message:
        flash("コメントを入力してください。", "error")
        return redirect(url_for("videos.watch", video_id=video_id))

    db.session.add(VideoComment(video_id=video_id, user_id=current_user.id, message=message[:500]))
    db.session.commit()
    if video.uploader_id != current_user.id:
        notify(video.uploader_id, f"{current_user.username}さんが「{video.title}」にコメントしました。")
    return redirect(url_for("videos.watch", video_id=video_id))


@videos_bp.route("/videos/<int:video_id>/like", methods=["POST"])
@login_required
def like(video_id):
    Video.query.get_or_404(video_id)
    is_like = request.form.get("is_like") == "1"

    existing = VideoLike.query.filter_by(video_id=video_id, user_id=current_user.id).first()
    if existing and existing.is_like == is_like:
        db.session.delete(existing)  # 同じボタンをもう一度押したら取り消す
    elif existing:
        existing.is_like = is_like
    else:
        db.session.add(VideoLike(video_id=video_id, user_id=current_user.id, is_like=is_like))
    db.session.commit()
    return redirect(url_for("videos.watch", video_id=video_id))


@videos_bp.route("/channel/<username>/subscribe", methods=["POST"])
@login_required
def subscribe(username):
    owner = User.query.filter_by(username=username).first_or_404()
    if owner.id == current_user.id:
        flash("自分のチャンネルは登録できません。", "error")
        return redirect(url_for("videos.channel", username=username))

    existing = ChannelSubscription.query.filter_by(subscriber_id=current_user.id, channel_owner_id=owner.id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        flash("チャンネル登録を解除しました。", "success")
    else:
        db.session.add(ChannelSubscription(subscriber_id=current_user.id, channel_owner_id=owner.id))
        db.session.commit()
        notify(owner.id, f"{current_user.username}さんがあなたのチャンネルに登録しました。")
        flash("チャンネル登録しました。", "success")
    return redirect(url_for("videos.channel", username=username))


@videos_bp.route("/channel/<username>")
@login_required
def channel(username):
    owner = User.query.filter_by(username=username).first_or_404()
    videos = Video.query.filter_by(uploader_id=owner.id).order_by(Video.created_at.desc()).all()
    subscriber_count = ChannelSubscription.query.filter_by(channel_owner_id=owner.id).count()
    is_subscribed = ChannelSubscription.query.filter_by(
        subscriber_id=current_user.id, channel_owner_id=owner.id
    ).first() is not None
    return render_template(
        "videos_channel.html", owner=owner, videos=videos,
        subscriber_count=subscriber_count, is_subscribed=is_subscribed,
    )


@videos_bp.route("/videos/<int:video_id>/watch-progress", methods=["POST"])
@login_required
def watch_progress(video_id):
    """
    再生中のプレイヤーから数秒おきに呼ばれ、新たに視聴した秒数を収益に加算する。
    同じ動画は、その動画自体の長さ分までしか収益として計上されない
    (=1本の動画につき、実質1回視聴した分だけ稼げる。再生を繰り返しても追加では稼げない)。
    また、直近で本人確認(CAPTCHA)に成功していない場合は、収益を一切加算しない
    (自動再生ツール・スクリプトによる収益稼ぎを防ぐため)。
    """
    from models import utcnow
    from datetime import datetime as _datetime

    video = Video.query.get_or_404(video_id)

    verified_until_raw = session.get(f"watch_verified_{video_id}")
    verified = False
    if verified_until_raw:
        try:
            verified = utcnow() < _datetime.fromisoformat(verified_until_raw)
        except Exception:
            verified = False
    if not verified:
        return jsonify({"ok": False, "needs_verification": True}), 403

    try:
        new_seconds = int(request.get_json(force=True).get("seconds", 0))
    except Exception:
        new_seconds = 0
    if new_seconds <= 0 or new_seconds > 30:
        # 1回のリクエストで加算できるのは常識的な範囲だけ(不正なリクエスト対策)
        return jsonify({"ok": False}), 400

    progress = VideoWatchProgress.query.filter_by(user_id=current_user.id, video_id=video_id).first()
    if not progress:
        progress = VideoWatchProgress(user_id=current_user.id, video_id=video_id, counted_seconds=0)
        db.session.add(progress)

    # 動画自体の長さ(video.duration_seconds)を超えては計上しない。
    # 長さが未取得(0)の場合は、安全側に倒して15分(アップロード上限)を仮の上限にする。
    cap_seconds = video.duration_seconds if video.duration_seconds > 0 else MAX_VIDEO_DURATION_SECONDS
    remaining_countable = max(0, cap_seconds - progress.counted_seconds)
    countable_now = min(new_seconds, remaining_countable)

    if countable_now > 0:
        progress.counted_seconds += countable_now
        current_user.video_watch_seconds_total += countable_now
        earned = (countable_now * EARNINGS_MILLIYEN_PER_MINUTE) // 60
        current_user.video_earnings_milliyen += earned
        db.session.commit()

    return jsonify({
        "ok": True, "counted_seconds": progress.counted_seconds,
        "total_earnings_yen": current_user.video_earnings_milliyen / 1000,
    })


@videos_bp.route("/videos/earnings")
@login_required
def earnings():
    my_requests = WithdrawalRequest.query.filter_by(user_id=current_user.id).order_by(WithdrawalRequest.created_at.desc()).all()
    return render_template(
        "videos_earnings.html", earnings_yen=current_user.video_earnings_milliyen / 1000,
        min_withdrawal=MIN_WITHDRAWAL_YEN, my_requests=my_requests,
        remaining_budget=_remaining_withdrawal_budget(),
    )


@videos_bp.route("/videos/earnings/budget-poll")
@login_required
def budget_poll():
    """残り出金可能額を、画面をリロードしなくてもリアルタイムに近い形で更新するためのポーリング用API"""
    remaining = _remaining_withdrawal_budget()
    return jsonify({"remaining_budget": remaining})


@videos_bp.route("/videos/earnings/withdraw", methods=["POST"])
@login_required
def request_withdrawal():
    destination = request.form.get("paypay_destination", "").strip()
    try:
        amount_yen = int(request.form.get("amount_yen", "0"))
    except ValueError:
        flash("出金額は数値で入力してください。", "error")
        return redirect(url_for("videos.earnings"))

    if not destination:
        flash("PayPayのID、または請求リンクのどちらかを入力してください。", "error")
        return redirect(url_for("videos.earnings"))
    if amount_yen < MIN_WITHDRAWAL_YEN:
        flash(f"最低出金額は{MIN_WITHDRAWAL_YEN}円です。", "error")
        return redirect(url_for("videos.earnings"))

    current_balance_yen = current_user.video_earnings_milliyen / 1000
    if amount_yen > current_balance_yen:
        flash("収益残高が足りません。", "error")
        return redirect(url_for("videos.earnings"))

    remaining_budget = _remaining_withdrawal_budget()
    if remaining_budget is not None and amount_yen > remaining_budget:
        flash(f"現在、運営の出金予算の都合上、この金額は申請できません(残り出金可能額: {remaining_budget}円)。しばらく経ってから再度お試しください。", "error")
        return redirect(url_for("videos.earnings"))

    current_user.video_earnings_milliyen -= amount_yen * 1000
    db.session.add(WithdrawalRequest(
        user_id=current_user.id, amount_yen=amount_yen, paypay_destination=destination,
    ))
    db.session.commit()

    flash(f"{amount_yen}円の出金申請を受け付けました。管理者が確認後、送金されます。", "success")
    return redirect(url_for("videos.earnings"))
