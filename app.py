from flask import Flask
from extensions import db, cors, swagger
from blueprints.api_v1 import api_v1
# Flask-JWT-Extended 임포트
from flask_jwt_extended import JWTManager
import os

def create_app():
    app = Flask(__name__)

    # DB 설정
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'data.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # 🔑 JWT 설정
    # 이전 SECRET_KEY 대신 JWT_SECRET_KEY 사용
    app.config['JWT_SECRET_KEY'] = 'super-secret-jwt-key-replace-me' # 실제 환경에서는 복잡하고 안전한 키 사용
    # Flask-Session 설정 제거 (JWT는 서버 세션 불필요)
    # app.config['SESSION_TYPE'] = 'filesystem' 

    # 확장 초기화
    db.init_app(app)
    cors.init_app(app)
    swagger.init_app(app)
    # Session(app) 제거
    
    # JWTManager 초기화
    jwt = JWTManager(app)

    # 블루프린트 등록
    app.register_blueprint(api_v1)

    return app


app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("✅ 모든 테이블 생성 완료")
    app.run(debug=True, port=5000)