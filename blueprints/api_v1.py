from flask import Blueprint, request, jsonify
from extensions import db
import datetime
from models import User
import datetime
# 🚨 ActivityRecord만 임포트
from models import User, ActivityRecord
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from functools import wraps
# JWT 관련 임포트
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from functools import wraps
from flask import current_app as app


# Blueprint 생성
api_v1 = Blueprint("api_v1", __name__, url_prefix="/v1/api")

# current_user_id 함수를 get_jwt_identity로 대체
def current_user_id():
    return int(get_jwt_identity())

# --- ActivityRecord (통합) ---

# 🚨 활동 기록 추가 (수동/자동 모두 처리)
@api_v1.route('/activity', methods=['POST'])
@jwt_required()
def add_activity_record():
    data = request.get_json()
    user_id = current_user_id()
    
    required_fields = ['title', 'start_time', 'end_time', 'type', 'duration_seconds']
    if not all(field in data for field in required_fields):
        return jsonify({'error': '필수 필드(title, start_time, end_time, type, duration_seconds) 누락'}), 400

    record_type = data['type'].upper()
    if record_type not in ['MANUAL', 'APP']:
         return jsonify({'error': "type은 'MANUAL' 또는 'APP'이어야 합니다."}), 400

    try:
        start_time_obj = datetime.datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
        end_time_obj = datetime.datetime.fromisoformat(data['end_time'].replace('Z', '+00:00'))
        
        # duration_seconds 검증 (클라이언트에서 보낸 값을 사용하되, 서버에서 한 번 더 확인)
        duration_from_time = (end_time_obj - start_time_obj).total_seconds()
        
        new_record = ActivityRecord(
            title=data['title'],
            type=record_type,
            start_time=start_time_obj,
            end_time=end_time_obj,
            duration_seconds=int(duration_from_time), # 서버에서 계산한 값 사용 권장
            memo=data.get('memo') if record_type == 'MANUAL' else None, # MANUAL 타입에만 memo 저장
            user_id=user_id
        )
        db.session.add(new_record)
        db.session.commit()
        return jsonify({'message': '활동 기록 추가 성공', 'record': new_record.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# 🚨 활동 기록 수정
@api_v1.route('/activity/<int:record_id>', methods=['PUT'])
@jwt_required()
def update_activity_record(record_id):
    data = request.get_json()
    user_id = current_user_id()
    record = ActivityRecord.query.filter_by(id=record_id, user_id=user_id).first()

    if not record:
        return jsonify({'error': '기록을 찾을 수 없거나 권한이 없습니다.'}), 404
        
    # APP 타입은 제목 외에는 수동으로 수정하지 않도록 제한할 수 있음 (여기서는 일단 허용)
    if record.type == 'APP' and ('memo' in data and data['memo'] is not None):
        return jsonify({'error': '앱 사용 기록은 메모를 수정할 수 없습니다.'}), 403


    try:
        record.title = data.get('title', record.title)
        
        start_time_str = data.get('start_time')
        if start_time_str:
            record.start_time = datetime.datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
        
        end_time_str = data.get('end_time')
        if end_time_str:
            record.end_time = datetime.datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))

        # MANUAL 타입에만 메모 업데이트 허용
        if record.type == 'MANUAL':
            record.memo = data.get('memo', record.memo)

        # 시간 변경 시 duration_seconds 재계산
        if start_time_str or end_time_str:
            if record.start_time and record.end_time:
                duration = (record.end_time - record.start_time).total_seconds()
                record.duration_seconds = int(duration)
        
        db.session.commit()
        return jsonify({'message': '활동 기록 업데이트 성공', 'record': record.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# 🚨 활동 기록 삭제
@api_v1.route('/activity/<int:record_id>', methods=['DELETE'])
@jwt_required()
def delete_activity_record(record_id):
    user_id = current_user_id()
    record = ActivityRecord.query.filter_by(id=record_id, user_id=user_id).first()

    if not record:
        return jsonify({'error': '기록을 찾을 수 없거나 권한이 없습니다.'}), 404

    try:
        db.session.delete(record)
        db.session.commit()
        return jsonify({'message': '기록 삭제 성공'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# 🚨 모든 활동 기록 조회
@api_v1.route('/activities', methods=['GET'])
@jwt_required()
def get_activity_records():
    user_id = current_user_id()
    # 최신 기록이 위로 오도록 내림차순 정렬
    records = ActivityRecord.query.filter_by(user_id=user_id).order_by(ActivityRecord.end_time.desc()).all()
    return jsonify([r.to_dict() for r in records])


# --- 회원가입 ---
@api_v1.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'username과 password 필수'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'error': '이미 존재하는 사용자'}), 400

    user = User(username=username)
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    return jsonify({'message': '회원가입 성공'}), 201


# --- 로그인 (JWT 토큰 발행) ---
@api_v1.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({'error': '아이디 또는 비밀번호가 잘못됨'}), 401

    # 로그인 성공 시, User ID를 Identity로 JWT 토큰 생성
    access_token = create_access_token(identity=str(user.id), expires_delta=False)
    
    # 토큰과 사용자 정보 반환
    return jsonify({
        'message': '로그인 성공', 
        'user': user.to_dict(), 
        'token': access_token # 토큰 추가 반환
    }), 200


# --- 로그아웃 (JWT는 서버에서 할 일이 없음. 클라이언트가 토큰을 버리면 됨.) ---
@api_v1.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    # 클라이언트에서 토큰을 삭제하도록 안내만 합니다.
    # 블랙리스트 기능을 사용하려면 추가 설정 필요
    return jsonify({'message': '로그아웃 성공'}), 200

# def current_user_id():
#     return session.get('user_id') # 사용 안함