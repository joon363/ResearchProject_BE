from flask import Flask
# 🚨 extensions.py에서 기존 'swagger'를 제거하고 'db', 'cors'만 사용합니다.
from extensions import db, cors 
from blueprints.api_v1 import api_v1
from flask_jwt_extended import JWTManager
import os
# 1. Flask-RESTX의 Api 클래스 임포트
from flask_restx import Api 

def create_app():
    app = Flask(__name__)

    # DB 설정
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'data.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # 🔑 JWT 설정
    app.config['JWT_SECRET_KEY'] = 'super-secret-jwt-key-replace-me'
    
    # 확장 초기화
    db.init_app(app)
    cors.init_app(app)
    # 2. 기존 swagger.init_app(app) 제거

    # JWTManager 초기화
    jwt = JWTManager(app)

    # 3. Flask-RESTX Api 객체 생성 및 설정
    # Api 객체는 /swagger/ 경로에 Swagger UI를 제공합니다.
    api = Api(
        app, 
        version='1.0', 
        title='Activity Tracking API',
        description='사용자의 활동 기록 및 인증을 위한 API 문서',
        doc='/apidocs/' # Swagger UI가 표시될 경로
    )

    # 4. JWT 인증을 위한 Security Definition 추가 (선택 사항이지만 권장됨)
    # 이는 Swagger UI에서 토큰을 입력할 수 있게 해줍니다.
    api.authorizations = {
        'jwt': {
            'type': 'apiKey',
            'in': 'header',
            'name': 'Authorization',
            'description': "JWT 토큰을 'Bearer <token>' 형식으로 입력하세요."
        }
    }

    # 5. 기존 블루프린트 등록 대신, Api 객체에 네임스페이스 등록
    # api_v1은 이제 Flask-RESTX Namespace입니다.
    api.add_namespace(api_v1)
    # app.register_blueprint(api_v1) # 🚨 이 줄은 제거해야 합니다.

    return app


app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("✅ 모든 테이블 생성 완료")
    app.run(debug=True, port=5000)