from flask_restx import Namespace, Resource, fields, reqparse
from extensions import db
import datetime
from models import User, ActivityRecord # ActivityRecord 모델 사용 가정
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from functools import wraps
from flask import jsonify, request # JSONIFY 및 request는 flask에서 계속 사용

# --- Flask-RESTX 네임스페이스 생성 ---
# 기존 Blueprint를 대체하며, API 경로와 설명을 지정합니다.
api_v1 = Namespace("api_v1", description="활동 기록 및 사용자 관리 API", path="/v1/api")

# current_user_id 함수 (변경 없음)
def current_user_id():
    """JWT 토큰에서 사용자 ID를 추출합니다."""
    # get_jwt_identity()는 문자열을 반환하므로 int로 변환
    return int(get_jwt_identity())

# JWT 인증 데코레이터 (필요 시 사용자 정의)
# 여기서는 `jwt_required()`를 직접 사용합니다.

# --- Flask-RESTX 모델 정의 (응답/요청 스키마) ---
# ActivityRecord의 응답 형식을 정의합니다.
activity_record_model = api_v1.model('ActivityRecord', {
    'id': fields.Integer(readonly=True, description='활동 기록 ID'),
    'user_id': fields.Integer(description='사용자 ID'),
    'title': fields.String(required=True, description='활동 제목'),
    'type': fields.String(required=True, enum=['MANUAL', 'APP'], description='기록 유형 (MANUAL 또는 APP)'),
    'start_time': fields.DateTime(required=True, description='시작 시간 (ISO 8601 형식)'),
    'end_time': fields.DateTime(required=True, description='종료 시간 (ISO 8601 형식)'),
    'duration_seconds': fields.Integer(required=True, description='활동 시간 (초)'),
    'memo': fields.String(description='메모 (MANUAL 타입에만 사용)'),
    'created_at': fields.DateTime(readonly=True, description='생성 시간'),
    'updated_at': fields.DateTime(readonly=True, description='수정 시간'),
})

activity_input_model = api_v1.model('ActivityInput', {
    'title': fields.String(required=True, description='활동 제목'),
    'start_time': fields.String(required=True, description='시작 시간 (ISO 8601 형식)'),
    'end_time': fields.String(required=True, description='종료 시간 (ISO 8601 형식)'),
    'type': fields.String(required=True, enum=['MANUAL', 'APP'], description='기록 유형'),
    'duration_seconds': fields.Integer(required=True, description='활동 시간 (초)'),
    'memo': fields.String(description='메모 (MANUAL 타입인 경우)'),
})

user_model = api_v1.model('User', {
    'id': fields.Integer(readonly=True, description='사용자 ID'),
    'username': fields.String(required=True, description='사용자 이름'),
})

# --- ActivityRecord 리소스 (통합) ---

@api_v1.route('/activity')
class ActivityList(Resource):
    @api_v1.doc(security='jwt')
    @api_v1.expect(activity_input_model)
    @api_v1.response(201, '활동 기록 추가 성공', activity_record_model)
    @api_v1.response(400, '요청 오류')
    @api_v1.response(401, '인증 실패')
    @jwt_required()
    def post(self):
        """🚨 활동 기록 추가 (수동/자동 모두 처리)"""
        data = request.json
        user_id = current_user_id()
        
        required_fields = ['title', 'start_time', 'end_time', 'type', 'duration_seconds']
        if not all(field in data for field in required_fields):
            return {'error': '필수 필드(title, start_time, end_time, type, duration_seconds) 누락'}, 400

        record_type = data['type'].upper()
        if record_type not in ['MANUAL', 'APP']:
            return {'error': "type은 'MANUAL' 또는 'APP'이어야 합니다."}, 400

        try:
            # 기존 Flask 코드 로직 유지
            start_time_obj = datetime.datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
            end_time_obj = datetime.datetime.fromisoformat(data['end_time'].replace('Z', '+00:00'))
            duration_from_time = (end_time_obj - start_time_obj).total_seconds()
            
            new_record = ActivityRecord(
                title=data['title'],
                type=record_type,
                start_time=start_time_obj,
                end_time=end_time_obj,
                duration_seconds=int(duration_from_time),
                memo=data.get('memo') if record_type == 'MANUAL' else None,
                user_id=user_id
            )
            db.session.add(new_record)
            db.session.commit()
            return {'message': '활동 기록 추가 성공', 'record': new_record.to_dict()}, 201
        except Exception as e:
            db.session.rollback()
            return {'error': str(e)}, 500

@api_v1.route('/activities')
class ActivityListAll(Resource):
    @api_v1.doc(security='jwt')
    @api_v1.response(200, '모든 활동 기록 조회 성공', [activity_record_model])
    @api_v1.response(401, '인증 실패')
    @jwt_required()
    def get(self):
        """🚨 모든 활동 기록 조회"""
        user_id = current_user_id()
        # 최신 기록이 위로 오도록 내림차순 정렬
        records = ActivityRecord.query.filter_by(user_id=user_id).order_by(ActivityRecord.end_time.desc()).all()
        return [r.to_dict() for r in records], 200

@api_v1.route('/activity/<int:record_id>')
@api_v1.param('record_id', '활동 기록 ID')
class ActivityDetail(Resource):
    
    @api_v1.doc(security='jwt')
    @api_v1.expect(activity_input_model, validate=False) # 부분 업데이트이므로 validate=False
    @api_v1.response(200, '활동 기록 업데이트 성공', activity_record_model)
    @api_v1.response(404, '기록을 찾을 수 없거나 권한이 없습니다.')
    @api_v1.response(403, '앱 사용 기록은 메모를 수정할 수 없습니다.')
    @api_v1.response(401, '인증 실패')
    @jwt_required()
    def put(self, record_id):
        """🚨 활동 기록 수정"""
        data = request.json
        user_id = current_user_id()
        record = ActivityRecord.query.filter_by(id=record_id, user_id=user_id).first()

        if not record:
            return {'error': '기록을 찾을 수 없거나 권한이 없습니다.'}, 404
            
        if record.type == 'APP' and ('memo' in data and data['memo'] is not None):
            return {'error': '앱 사용 기록은 메모를 수정할 수 없습니다.'}, 403

        try:
            # 기존 Flask 코드 로직 유지
            record.title = data.get('title', record.title)
            
            start_time_str = data.get('start_time')
            if start_time_str:
                record.start_time = datetime.datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            
            end_time_str = data.get('end_time')
            if end_time_str:
                record.end_time = datetime.datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))

            if record.type == 'MANUAL':
                record.memo = data.get('memo', record.memo)

            if start_time_str or end_time_str:
                if record.start_time and record.end_time:
                    duration = (record.end_time - record.start_time).total_seconds()
                    record.duration_seconds = int(duration)
            
            db.session.commit()
            return {'message': '활동 기록 업데이트 성공', 'record': record.to_dict()}, 200
        except Exception as e:
            db.session.rollback()
            return {'error': str(e)}, 500

    @api_v1.doc(security='jwt')
    @api_v1.response(200, '기록 삭제 성공')
    @api_v1.response(404, '기록을 찾을 수 없거나 권한이 없습니다.')
    @api_v1.response(401, '인증 실패')
    @jwt_required()
    def delete(self, record_id):
        """🚨 활동 기록 삭제"""
        user_id = current_user_id()
        record = ActivityRecord.query.filter_by(id=record_id, user_id=user_id).first()

        if not record:
            return {'error': '기록을 찾을 수 없거나 권한이 없습니다.'}, 404

        try:
            db.session.delete(record)
            db.session.commit()
            return {'message': '기록 삭제 성공'}, 200
        except Exception as e:
            db.session.rollback()
            return {'error': str(e)}, 500

# --- 사용자 리소스 ---

@api_v1.route('/register')
class UserRegister(Resource):
    @api_v1.expect(api_v1.model('RegisterInput', {'username': fields.String(required=True), 'password': fields.String(required=True)}))
    @api_v1.response(201, '회원가입 성공')
    @api_v1.response(400, '요청 오류 또는 이미 존재하는 사용자')
    def post(self):
        """회원가입"""
        data = request.json
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return {'error': 'username과 password 필수'}, 400

        if User.query.filter_by(username=username).first():
            return {'error': '이미 존재하는 사용자'}, 400

        user = User(username=username)
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        return {'message': '회원가입 성공'}, 201


@api_v1.route('/login')
class UserLogin(Resource):
    @api_v1.expect(api_v1.model('LoginInput', {'username': fields.String(required=True), 'password': fields.String(required=True)}))
    @api_v1.response(200, '로그인 성공', api_v1.model('LoginResponse', {'message': fields.String, 'user': fields.Nested(user_model), 'token': fields.String}))
    @api_v1.response(401, '아이디 또는 비밀번호가 잘못됨')
    def post(self):
        """로그인 (JWT 토큰 발행)"""
        data = request.json
        username = data.get('username')
        password = data.get('password')

        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            return {'error': '아이디 또는 비밀번호가 잘못됨'}, 401

        access_token = create_access_token(identity=str(user.id), expires_delta=False)
        
        return {
            'message': '로그인 성공', 
            'user': user.to_dict(), 
            'token': access_token
        }, 200

@api_v1.route('/logout')
class UserLogout(Resource):
    @api_v1.doc(security='jwt')
    @api_v1.response(200, '로그아웃 성공')
    @api_v1.response(401, '인증 실패')
    @jwt_required()
    def post(self):
        """로그아웃"""
        # JWT는 서버에서 할 일이 없음. 클라이언트가 토큰을 버리면 됨.
        return {'message': '로그아웃 성공'}, 200