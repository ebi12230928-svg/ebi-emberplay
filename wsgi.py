"""
本番用WSGIサーバー(gunicornなど)から読み込むためのエントリポイント。
Railwayなどでは `gunicorn wsgi:app` のように起動する。
"""
from app import create_app

app = create_app()
