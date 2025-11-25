from flask import Blueprint, request, jsonify
from extensions import db
import datetime

# Blueprint 생성
api_v1 = Blueprint("api_v1", __name__, url_prefix="/v1/api")

# 모델 임포트용
from models import TimeRecord, AppUsage


# --- API 1: Flutter 앱용 (기존) ---
@api_v1.route('/record', methods=['POST'])
def add_record():
    """
    Add time record
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          id: TimeRecord
          required: 
            - hour
            - minute
          properties:
            hour:
              type: integer
            minute:
              type: integer
    responses:
      201:
        description: Record added
    """
    data = request.get_json()
    new_record = TimeRecord(hour=data['hour'], minute=data['minute'])
    db.session.add(new_record)
    db.session.commit()
    return jsonify({'message': '기록 추가 성공'}), 201


@api_v1.route('/records', methods=['GET'])
def get_records():
    """
    Get all time records
    ---
    responses:
      200:
        description: List of records
    """
    records = TimeRecord.query.all()
    return jsonify([r.to_dict() for r in records])


# --- API 2: Windows 트래커용 (신규) ---
@api_v1.route('/usage', methods=['POST'])
def add_app_usage():
    """
    Add app usage log
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          id: AppUsage
    """
    data = request.get_json()
    try:
        start_time_obj = datetime.datetime.fromisoformat(data['start_time'])
        end_time_obj = datetime.datetime.fromisoformat(data['end_time'])

        new_usage = AppUsage(
            app_name=data['app_name'],
            start_time=start_time_obj,
            end_time=end_time_obj,
            duration_seconds=int(data['duration_seconds'])
        )
        db.session.add(new_usage)
        db.session.commit()

        return jsonify({'message': '사용 기록 추가 성공'}), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_v1.route('/usages', methods=['GET'])
def get_app_usages():
    """
    Get app usage logs
    ---
    responses:
      200:
        description: List of apps usage logs
    """
    usages = AppUsage.query.order_by(AppUsage.id.desc()).all()
    return jsonify([u.to_dict() for u in usages])
