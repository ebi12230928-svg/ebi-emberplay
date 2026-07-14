"""
リズムゲーム。管理者がYouTube動画(楽曲)を登録し、プレイヤーはYouTube公式プレイヤーで
再生される楽曲に合わせて、BPMから自動生成される譜面のノーツをタップする。
著作権保護のため、音源そのものはダウンロード・保存せず、常にYouTube公式プレイヤーで再生する。
難易度は太鼓の達人を参考に「かんたん・ふつう・むずかしい・おに」の4段階。曲ごとに使える難易度を管理者が設定できる。
"""
import json
import re
import random

from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user

from extensions import db
from models import RhythmSong, RhythmScore

rhythm_bp = Blueprint("rhythm", __name__)

# 太鼓の達人を参考にした4段階の難易度
DIFFICULTIES = {
    "easy": {"label": "かんたん", "color": "#4caf6d", "note_interval_beats": 2},
    "normal": {"label": "ふつう", "color": "#3b82f6", "note_interval_beats": 1},
    "hard": {"label": "むずかしい", "color": "#f59e0b", "note_interval_beats": 0.5},
    "oni": {"label": "おに", "color": "#dc2626", "note_interval_beats": 0.25},
}
DIFFICULTY_ORDER = ["easy", "normal", "hard", "oni"]
LANES = 4


def _song_difficulties(song):
    try:
        keys = json.loads(song.available_difficulties_json)
    except (TypeError, ValueError):
        keys = list(DIFFICULTIES.keys())
    return [k for k in DIFFICULTY_ORDER if k in keys]


def _length_options(song):
    """曲ごとに選べる「どこまで遊ぶか」の選択肢(区切りが設定されている分だけ表示)"""
    options = []
    if song.verse1_end_seconds:
        options.append({"key": "verse1", "label": "1番まで", "seconds": song.verse1_end_seconds})
    if song.verse2_end_seconds:
        options.append({"key": "verse2", "label": "2番まで", "seconds": song.verse2_end_seconds})
    options.append({"key": "full", "label": "最後まで", "seconds": song.duration_seconds})
    return options


def _extract_youtube_id(text):
    """YouTubeのURL(様々な形式)、または動画IDそのものから、動画IDだけを取り出す"""
    text = text.strip()
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtube\.com/live/|youtube\.com/shorts/|youtube\.com/embed/|youtu\.be/)([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
        return text
    return None


QUICK_PLAY_BPM = 120  # ユーザーが自分のURLで遊ぶ時は、実際のBPMを解析できないため固定値を使う


def _generate_notes(bpm, offset, play_seconds, difficulty, seed=None):
    """
    レーンをしっかり全て使い、同じレーンが連続しすぎないように生成する。
    難易度が高いほど、プロセカのような「長押し(ホールド)」ノーツも混ざるようにする。
    """
    rng = random.Random(seed)  # 同じ曲・難易度・区間なら毎回同じ譜面になるようにシードを固定する
    interval_beats = DIFFICULTIES[difficulty]["note_interval_beats"]
    beat_seconds = 60 / bpm
    note_gap = beat_seconds * interval_beats
    hold_chance = {"easy": 0.0, "normal": 0.08, "hard": 0.15, "oni": 0.22}.get(difficulty, 0.1)

    notes = []
    t = max(2.0, offset)
    last_lane = -1
    recent_lanes = []
    while t < play_seconds - 1:
        # 直近を含めて同じレーンばかりにならないよう、まんべんなく全レーンを使う
        candidates = [l for l in range(LANES) if l != last_lane and recent_lanes.count(l) < 2]
        if not candidates:
            candidates = [l for l in range(LANES) if l != last_lane]
        lane = rng.choice(candidates)

        note = {"time": round(t, 2), "lane": lane}
        if hold_chance > 0 and rng.random() < hold_chance:
            hold_beats = rng.choice([1, 1.5, 2])
            note["hold"] = round(beat_seconds * hold_beats, 2)

        notes.append(note)
        last_lane = lane
        recent_lanes.append(lane)
        if len(recent_lanes) > 3:
            recent_lanes.pop(0)

        t += note_gap + note.get("hold", 0)  # ロングノーツの分、次のノーツまでの間隔を空ける
    return notes


@rhythm_bp.route("/rhythm/quick-play", methods=["POST"])
@login_required
def quick_play():
    """
    ユーザーが自分でYouTubeのURLを貼り付けて、その場でリズムゲームを始められる機能。
    BPM・開始位置(イントロを飛ばす秒数)を自分で指定できるので、知っている曲ならしっかり合わせられる。
    未入力の場合は標準テンポ(120)で生成する。
    """
    url_input = request.form.get("youtube_url", "").strip()
    difficulty = request.form.get("difficulty", "normal")
    try:
        duration = max(10, min(600, int(request.form.get("duration_seconds", "90"))))
    except (TypeError, ValueError):
        duration = 90
    try:
        bpm_raw = request.form.get("bpm", "").strip()
        bpm = max(40, min(300, int(bpm_raw))) if bpm_raw else QUICK_PLAY_BPM
    except (TypeError, ValueError):
        bpm = QUICK_PLAY_BPM
    try:
        offset_raw = request.form.get("offset_seconds", "").strip()
        offset = max(0.0, float(offset_raw)) if offset_raw else 0.0
    except (TypeError, ValueError):
        offset = 0.0
    if difficulty not in DIFFICULTIES:
        difficulty = "normal"

    youtube_id = _extract_youtube_id(url_input)
    if not youtube_id:
        songs = RhythmSong.query.filter_by(is_active=True).order_by(RhythmSong.created_at.desc()).all()
        song_info = {s.id: {"difficulties": _song_difficulties(s), "lengths": _length_options(s)} for s in songs}
        return render_template(
            "rhythm.html", songs=songs, difficulties=DIFFICULTIES, song_info=song_info,
            error="YouTubeのURLから動画IDを読み取れませんでした。URLをそのまま貼り付けてみてください。",
        )

    notes = _generate_notes(bpm, offset, duration, difficulty, seed=youtube_id + difficulty)

    # クイックプレイ用の、DBに保存しない「その場限りの曲」情報
    fake_song = type("FakeSong", (), {
        "id": 0, "title": "あなたが選んだ曲", "youtube_id": youtube_id,
        "duration_seconds": duration, "bpm": bpm,
    })()

    return render_template(
        "rhythm_play.html", song=fake_song, difficulty=difficulty, difficulty_label=DIFFICULTIES[difficulty]["label"],
        notes_json=notes, lanes=LANES, play_seconds=duration, length_key="full", is_quick_play=True,
    )


@rhythm_bp.route("/rhythm")
@login_required
def index():
    songs = RhythmSong.query.filter_by(is_active=True).order_by(RhythmSong.created_at.desc()).all()
    song_info = {
        s.id: {"difficulties": _song_difficulties(s), "lengths": _length_options(s)}
        for s in songs
    }
    return render_template("rhythm.html", songs=songs, difficulties=DIFFICULTIES, song_info=song_info)


@rhythm_bp.route("/rhythm/play/<int:song_id>")
@login_required
def play(song_id):
    song = RhythmSong.query.get(song_id)
    if not song or not song.is_active:
        return render_template("rhythm.html", songs=[], difficulties=DIFFICULTIES, song_info={}, error="この楽曲は見つかりません。")

    difficulty = request.args.get("difficulty", "normal")
    if difficulty not in _song_difficulties(song):
        difficulty = _song_difficulties(song)[0] if _song_difficulties(song) else "normal"

    length_key = request.args.get("length", "full")
    length_options = {o["key"]: o["seconds"] for o in _length_options(song)}
    play_seconds = length_options.get(length_key, song.duration_seconds)

    offset = max(0.0, song.offset_seconds or 0.0)
    notes = _generate_notes(song.bpm, offset, play_seconds, difficulty, seed=f"{song.id}-{difficulty}-{length_key}")

    return render_template(
        "rhythm_play.html", song=song, difficulty=difficulty, difficulty_label=DIFFICULTIES[difficulty]["label"],
        notes_json=notes, lanes=LANES, play_seconds=play_seconds, length_key=length_key,
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
        play_seconds = max(1, int(data.get("play_seconds", 90)))
    except (TypeError, ValueError):
        return jsonify({"error": "不正なスコアです。"}), 400

    is_quick_play = not song_id  # song_id が 0 / None の場合はクイックプレイ(その場限りの曲)
    if is_quick_play:
        try:
            bpm = max(40, min(300, int(data.get("bpm", QUICK_PLAY_BPM))))
        except (TypeError, ValueError):
            bpm = QUICK_PLAY_BPM
    else:
        song = RhythmSong.query.get(song_id)
        if not song:
            return jsonify({"error": "楽曲が見つかりません。"}), 400
        bpm = song.bpm

    # 難易度が上がるほどノーツが増える(=理論上の最大コンボ数も増える)ことを考慮して不正防止の上限を計算する
    interval_beats = DIFFICULTIES.get(difficulty, DIFFICULTIES["normal"])["note_interval_beats"]
    beat_seconds = 60 / bpm
    note_gap = max(0.05, beat_seconds * interval_beats)
    theoretical_notes = int(play_seconds / note_gap) + 5
    theoretical_max = theoretical_notes * 300 + 500
    if score > theoretical_max:
        return jsonify({"error": "スコアが不正です。"}), 400
    if max_combo > theoretical_notes:
        return jsonify({"error": "コンボ数が不正です。"}), 400

    if not is_quick_play:
        db.session.add(RhythmScore(
            user_id=current_user.id, song_id=song_id, difficulty=difficulty, score=score, max_combo=max_combo
        ))

    # 報酬は最大コンボ数のみを基準にする(10コンボにつき500ポイント)。曲の長さに関わらず一律この計算方式。
    # スコアの多寡ではなくコンボ数で決めるため、短い曲を繰り返して稼ぐようなことができない。
    difficulty_mult = {"easy": 1.0, "normal": 1.3, "hard": 1.7, "oni": 2.2}.get(difficulty, 1.0)
    reward = round((max_combo // 10) * 500 * difficulty_mult)
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
