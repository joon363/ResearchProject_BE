from flask import Flask
from extensions import db, cors, swagger
from blueprints.api_v1 import api_v1
import os

def create_app():
    app = Flask(__name__)

    # DB 설정
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'data.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # 확장 초기화
    db.init_app(app)
    cors.init_app(app)
    swagger.init_app(app)

    # 블루프린트 등록
    app.register_blueprint(api_v1)

    return app


app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
