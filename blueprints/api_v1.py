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
    'app': fields.String(required=True, description='앱 이름'),
    'start_time': fields.DateTime(required=True, description='시작 시간 (ISO 8601 형식)'),
    'end_time': fields.DateTime(required=True, description='종료 시간 (ISO 8601 형식)'),
    'duration_seconds': fields.Integer(required=True, description='활동 시간 (초)'),
    'memo': fields.String(description='메모'),
    'created_at': fields.DateTime(readonly=True, description='생성 시간'),
    'updated_at': fields.DateTime(readonly=True, description='수정 시간'),
})

activity_input_model = api_v1.model('ActivityInput', {
    'title': fields.String(required=True, description='활동 제목'),
    'start_time': fields.String(required=True, description='시작 시간 (ISO 8601 형식)'),
    'end_time': fields.String(required=True, description='종료 시간 (ISO 8601 형식)'),
    'app': fields.String(required=True, description='앱 이름'),
    'duration_seconds': fields.Integer(required=True, description='활동 시간 (초)'),
    'memo': fields.String(description='메모'),
})

user_model = api_v1.model('User', {
    'id': fields.Integer(readonly=True, description='사용자 ID'),
    'username': fields.String(required=True, description='사용자 이름'),
})

# 응답 모델: 일별 활동 시간 집계
daily_summary_model = api_v1.model('DailySummary', {
    'date': fields.String(description='YYYY-MM-DD 형식의 날짜'),
    'total_seconds': fields.Integer(description='해당 날짜의 총 활동 시간 (초)'),
})

# 응답 모델: 활동 제목별 총 시간 집계
activity_summary_model = api_v1.model('ActivitySummary', {
    'title': fields.String(description='활동 제목'),
    'total_seconds': fields.Integer(description='총 활동 시간 (초)'),
    'records': fields.List(fields.Nested(activity_record_model), description='해당 활동의 최근 기록 목록')
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
        
        required_fields = ['title', 'start_time', 'end_time', 'app', 'duration_seconds']
        if not all(field in data for field in required_fields):
            return {'error': '필수 필드(title, start_time, end_time, app, duration_seconds) 누락'}, 400

        try:
            # 기존 Flask 코드 로직 유지
            start_time_obj = datetime.datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
            end_time_obj = datetime.datetime.fromisoformat(data['end_time'].replace('Z', '+00:00'))
            duration_from_time = (end_time_obj - start_time_obj).total_seconds()
            
            new_record = ActivityRecord(
                title=data['title'],
                app=data['app'],
                start_time=start_time_obj,
                end_time=end_time_obj,
                duration_seconds=int(duration_from_time),
                memo=data.get('memo'),
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

        try:
            # 기존 Flask 코드 로직 유지
            record.title = data.get('title', record.title)
            record.app = data.get('app', record.app)
            
            start_time_str = data.get('start_time')
            if start_time_str:
                record.start_time = datetime.datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            
            end_time_str = data.get('end_time')
            if end_time_str:
                record.end_time = datetime.datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))

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
    

@api_v1.route('/activities/summary')
class ActivitySummary(Resource):
    @api_v1.doc(security='jwt')
    @api_v1.param('days', '조회할 기간 (일, 기본값 7일)', type=int)
    @api_v1.response(200, '주요 활동 및 일간 집계 조회 성공', api_v1.model('DashboardSummary', {
        'top_activities': fields.List(fields.Nested(activity_summary_model), description='주요 활동 집계'),
        'daily_breakdown': fields.List(fields.Nested(daily_summary_model), description='일별 총 시간 집계'),
    }))
    @jwt_required()
    def get(self):
        """🚨 지난 N일간의 일별 총 활동 시간 및 주요 활동 목록 조회"""
        user_id = current_user_id()
        parser = reqparse.RequestParser()
        parser.add_argument('days', type=int, default=7, location='args')
        args = parser.parse_args()
        
        days = args['days']
        
        # 1. 날짜 범위 설정
        now = datetime.datetime.utcnow()
        start_date = now - datetime.timedelta(days=days)
        
        # 2. 범위 내 ActivityRecord 조회
        records = ActivityRecord.query.filter(
            ActivityRecord.user_id == user_id,
            ActivityRecord.end_time >= start_date,
        ).order_by(ActivityRecord.end_time.desc()).all()

        # 3. 일별 총 시간 집계 (Daily Breakdown)
        daily_seconds = {}
        # N일치 데이터 구조 초기화
        for i in range(days):
            date = (now - datetime.timedelta(days=i)).date()
            daily_seconds[date.isoformat()] = 0
            
        for record in records:
            date_str = record.end_time.date().isoformat()
            daily_seconds[date_str] = daily_seconds.get(date_str, 0) + record.duration_seconds
            
        daily_breakdown = [
            {'date': date, 'total_seconds': seconds}
            for date, seconds in sorted(daily_seconds.items())
        ]
        
        # 4. 활동 제목별 총 시간 집계 (Top Activities for Chart/Legend)
        activity_breakdown = {}
        for record in records:
            title = record.title
            if title not in activity_breakdown:
                activity_breakdown[title] = {
                    'total_seconds': 0,
                    'records': [] # 해당 활동의 모든 기록을 저장
                }
            activity_breakdown[title]['total_seconds'] += record.duration_seconds
            activity_breakdown[title]['records'].append(record)
            
        # 상위 랭킹순으로 정렬
        sorted_activities = sorted(
            activity_breakdown.items(), 
            key=lambda item: item[1]['total_seconds'], 
            reverse=True
        )
        
        top_activities = []
        for title, data in sorted_activities:
            # 기록은 최신 3개만 반환
            recent_records = sorted(data['records'], key=lambda r: r.end_time, reverse=True)[:3]
            
            # 여기서 ActivityRecord 대신 ActivitySummaryItem 모델을 반환하도록 설계 변경 가능
            # 현재는 단순화를 위해 title과 total_seconds만 반환하고, 클라이언트에서 처리하도록 합니다.
            top_activities.append({
                'title': title,
                'total_seconds': data['total_seconds'],
                # 클라이언트의 차트 로직을 위해 records를 반환하면 좋지만, 데이터가 너무 커지므로
                # 일단 records 필드는 제거하고 title과 total_seconds만 반환합니다.
                # 'records': [r.to_dict() for r in recent_records] 
            })

        # --- 차트 데이터 구조를 위한 추가 집계 ---
        # 클라이언트에서 스택형 차트를 그리기 위해, 일별 활동 데이터를 상세하게 제공합니다.
        
        # Daily Stack Breakdown
        daily_stack_breakdown = {}
        for i in range(days):
            date = (now - datetime.timedelta(days=i)).date().isoformat()
            daily_stack_breakdown[date] = {}
        
        # { 'YYYY-MM-DD': { 'PintOS 구현': 3600, '알고리즘 문제 풀이': 1800, ... } }
        for record in records:
            date_str = record.end_time.date().isoformat()
            title = record.title
            daily_stack_breakdown[date_str] = daily_stack_breakdown.get(date_str, {})
            daily_stack_breakdown[date_str][title] = daily_stack_breakdown[date_str].get(title, 0) + record.duration_seconds

        return {
            'daily_total_summary': daily_breakdown, # 일별 총 시간 (선 그래프나 요약용)
            'top_activities': top_activities,       # 상위 활동 목록 (범례용)
            'daily_stack_breakdown': daily_stack_breakdown, # 일별 스택 차트 데이터
        }, 200

# --- 단일 기록 상세 조회 기능 추가 ---
@api_v1.route('/activity/<int:record_id>')
# ... (ActivityDetail 클래스 유지 및 get 메서드 추가) ...
class ActivityDetail(Resource):
    
    # ... (put, delete 메서드 유지) ...
    
    @api_v1.doc(security='jwt')
    @api_v1.response(200, '단일 활동 기록 조회 성공', activity_record_model)
    @api_v1.response(404, '기록을 찾을 수 없거나 권한이 없습니다.')
    @api_v1.response(401, '인증 실패')
    @jwt_required()
    def get(self, record_id):
        """🚨 단일 활동 기록 상세 조회"""
        user_id = current_user_id()
        record = ActivityRecord.query.filter_by(id=record_id, user_id=user_id).first()
        
        if not record:
            return {'error': '기록을 찾을 수 없거나 권한이 없습니다.'}, 404
            
        return record.to_dict(), 200