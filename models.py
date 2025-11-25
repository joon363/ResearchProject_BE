from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
import datetime

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

    # 🚨 TimeRecord와 AppUsage 관계 제거
    # time_records = db.relationship('TimeRecord', backref='user', lazy=True)
    # app_usages = db.relationship('AppUsage', backref='user', lazy=True)
    
    # 🚨 ActivityRecord 관계 추가
    activity_records = db.relationship('ActivityRecord', backref='user', lazy=True)


    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {'id': self.id, 'username': self.username}


# 🚨 ActivityRecord 모델 (TimeRecord + AppUsage 통합)
class ActivityRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    # 🚨 공통 필드 (TimeRecord의 title, AppUsage의 app_name을 포함)
    title = db.Column(db.String(100), nullable=False) # 수동 기록 제목 또는 앱 이름
    start_time = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    duration_seconds = db.Column(db.Integer, nullable=False, default=0)
    
    # 🚨 TimeRecord 전용 필드
    memo = db.Column(db.Text, nullable=True) # 수동 기록 메모 (앱 사용 기록 시에는 null)
    
    # 🚨 AppUsage 전용 필드 및 타입 분류 필드
    type = db.Column(db.String(20), nullable=False) # 'MANUAL' (수동) 또는 'APP' (자동)
    
    # app_name 필드는 title로 통합하여 사용
    # app_category = db.Column(db.String(50), nullable=True) # 확장성을 위한 카테고리 (현재는 사용 안함)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'type': self.type, # 타입 추가
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration_seconds': self.duration_seconds,
            'memo': self.memo,
            'user_id': self.user_id
        }

# 🚨 기존 TimeRecord 및 AppUsage 모델 제거

# class TimeRecord(db.Model):
#     ...
# class AppUsage(db.Model):
#     ...