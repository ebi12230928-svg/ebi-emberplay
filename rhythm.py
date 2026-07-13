"""
リズムゲーム。管理者がYouTube動画(楽曲)を登録し、プレイヤーはYouTube公式プレイヤーで
再生される楽曲に合わせて、BPMから自動生成される譜面のノーツをタップする。
著作権保護のため、音源そのものはダウンロード・保存せず、常にYouTube公式プレイヤーで再生する。
"""
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user

from extensions import db
from models import RhythmSong, RhythmScore

rhythm_bp = Blueprint("rhythm", __name__)

DIFFICULTIES = {
    "easy": {"label": "EASY", "note_interval_beats": 2},
    "normal": {"label": "NORMAL", "note_interval_beats": 1},
    "hard": {"label": "HARD", "note_interval_beats": 0.5},
}
LANES = 4


@rhythm_bp.route("/rhythm")
@login_required
def index():
    songs = RhythmSong.query.filter_by(is_active=True).order_by(RhythmSong.created_at.desc()).all()
    return render_template("rhythm.html", songs=songs, difficulties=DIFFICULTIES)


@rhythm_bp.route("/rhythm/play/<int:song_id>")
@login_required
def play(song_id):
    song = RhythmSong.query.get(song_id)
    if not song or not song.is_active:
        return render_template("rhythm.html", songs=[], difficulties=DIFFICULTIES, error="この楽曲は見つかりません。")
    difficulty = request.args.get("difficulty", "normal")
    if difficulty not in DIFFICULTIES:
        difficulty = "normal"

    interval_beats = DIFFICULTIES[difficulty]["note_interval_beats"]
    beat_seconds = 60 / song.bpm
    note_gap = beat_seconds * interval_beats
    notes = []
    t = 2.0
    i = 0
    while t < song.duration_seconds - 1:
        lane = (i * 7 + i * i) % LANES
        notes.append({"time": round(t, 2), "lane": lane})
        t += note_gap
        i += 1

    return render_template(
        "rhythm_play.html", song=song, difficulty=difficulty,
        notes_json=notes, lanes=LANES,
    )


@rhythm_bp.route("/rhythm/submit-score", methods=["POST"])
@login_required
def submit_score():
    data = request.get_json(force=True)
    song_id = data.get("song_id")
    difficulty = data.get("difficulty", "normal")
    try:
        score = max(0, int(data.get("score", 0)))
        max_combo = max(0, int(data.get("max_combo", 0)))
    except (TypeError, ValueError):
        return jsonify({"error": "不正なスコアです。"}), 400

    song = RhythmSong.query.get(song_id)
    if not song:
        return jsonify({"error": "楽曲が見つかりません。"}), 400

    theoretical_max = int(song.duration_seconds / 0.4) * 300 + 500
    if score > theoretical_max:
        return jsonify({"error": "スコアが不正です。"}), 400

    db.session.add(RhythmScore(
        user_id=current_user.id, song_id=song_id, difficulty=difficulty, score=score, max_combo=max_combo
    ))

    reward = min(300, round(score / 20))
    from games.common import credit_reward
    credit_reward(current_user, reward)
    db.session.commit()

    return jsonify({"ok": True, "reward": reward, "balance": current_user.balance})


@rhythm_bp.route("/rhythm/leaderboard/<int:song_id>")
@login_required
def leaderboard(song_id):
    top = (
        RhythmScore.query.filter_by(song_id=song_id)
        .order_by(RhythmScore.score.desc()).limit(10).all()
    )
    return jsonify({"scores": [{"username": s.user_id, "score": s.score, "difficulty": s.difficulty} for s in top]})
