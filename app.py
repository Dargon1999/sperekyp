import os
import logging
import shutil
import zipfile
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity, set_access_cookies, unset_jwt_cookies
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename
from PIL import Image
import json
import hashlib

# Get the directory where app.py is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, 
            template_folder=BASE_DIR, 
            static_folder=BASE_DIR, 
            static_url_path='')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(BASE_DIR, "admin.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'dev-key-moneytracker-pro-2026' 
app.config['JWT_TOKEN_LOCATION'] = ['cookies']
app.config['JWT_COOKIE_CSRF_PROTECT'] = False 
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'uploads')
app.config['BACKUP_FOLDER'] = os.path.join(BASE_DIR, 'backups')
app.config['TRASH_FOLDER'] = os.path.join(BASE_DIR, 'trash')
app.config['MAX_CONTENT_LENGTH'] = 30 * 1024 * 1024 # 30MB

# Ensure directories exist
for folder in [app.config['UPLOAD_FOLDER'], 
               os.path.join(app.config['UPLOAD_FOLDER'], 'images'),
               os.path.join(app.config['UPLOAD_FOLDER'], 'previews'),
               os.path.join(app.config['UPLOAD_FOLDER'], 'software'),
               app.config['BACKUP_FOLDER'],
               app.config['TRASH_FOLDER']]:
    os.makedirs(folder, exist_ok=True)

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per day", "50 per hour"], storage_uri="memory://")

# Models
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

class AdminLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    ip = db.Column(db.String(45))
    action = db.Column(db.String(255))

class ImageMetadata(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), unique=True, nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    mimetype = db.Column(db.String(50), nullable=False)
    size = db.Column(db.Integer, nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    is_hero = db.Column(db.Boolean, default=False)
    is_bg = db.Column(db.Boolean, default=False)
    # New fields
    name = db.Column(db.String(255))
    description = db.Column(db.Text)
    priority = db.Column(db.Integer, default=0)
    hash = db.Column(db.String(64), unique=True) # SHA-256 hash

# Initialize database and admin user
with app.app_context():
    try:
        db.create_all()
        # Add missing columns for ImageMetadata if they don't exist (simple migration)
        try:
            from sqlalchemy import text
            with db.engine.connect() as conn:
                # SQLite-specific migration
                columns = [c[1] for c in conn.execute(text("PRAGMA table_info(image_metadata)")).fetchall()]
                if 'name' not in columns:
                    conn.execute(text("ALTER TABLE image_metadata ADD COLUMN name VARCHAR(255)"))
                if 'description' not in columns:
                    conn.execute(text("ALTER TABLE image_metadata ADD COLUMN description TEXT"))
                if 'priority' not in columns:
                    conn.execute(text("ALTER TABLE image_metadata ADD COLUMN priority INTEGER DEFAULT 0"))
                if 'hash' not in columns:
                    conn.execute(text("ALTER TABLE image_metadata ADD COLUMN hash VARCHAR(64) UNIQUE"))
                conn.commit()
        except Exception as e:
            logging.warning(f"Migration warning: {e}")

        if not Admin.query.filter_by(username='BossDargon').first():
            hashed_pw = bcrypt.generate_password_hash('Sanya0811').decode('utf-8')
            new_admin = Admin(username='BossDargon', password_hash=hashed_pw)
            db.session.add(new_admin)
            db.session.commit()
            logging.info("Database initialized and default admin 'BossDargon' created.")
    except Exception as e:
        logging.error(f"CRITICAL: Database initialization failed: {e}")

# Logging and Helpers
logging.basicConfig(filename='admin_activity.log', level=logging.INFO)

def log_action(action):
    try:
        ip = request.remote_addr
        log = AdminLog(ip=ip, action=action)
        db.session.add(log)
        db.session.commit()
        logging.info(f"{datetime.utcnow()} | IP: {ip} | Action: {action}")
    except Exception as e:
        logging.error(f"Logging failed: {e}")

def calculate_sha256(filepath):
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

# Routes
@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/admin')
@app.route('/admin.html')
def admin_page():
    return send_from_directory(BASE_DIR, 'admin.html')

@app.route('/dashboard')
@app.route('/dashboard.html')
@jwt_required(optional=True)
def dashboard_page():
    # Проверка JWT для защиты на сервере
    identity = get_jwt_identity()
    if not identity and window_protocol() != 'file:':
        return redirect('/admin')
    return send_from_directory(BASE_DIR, 'dashboard.html')

def window_protocol():
    # Вспомогательная функция для определения протокола (эмуляция для Flask)
    return request.headers.get('X-Forwarded-Proto', 'http')

@app.route('/api/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    try:
        data = request.json
        if not data:
            return jsonify({'msg': 'Отсутствуют данные JSON'}), 400
            
        username = data.get('username')
        password = data.get('password')
        
        logging.info(f"Login attempt for user: {username}")
        
        # Жестко заданные учетные данные: BossDargon / Sanya0811
        if username == "BossDargon" and password == "Sanya0811":
            access_token = create_access_token(identity=username)
            log_action(f"Successful login (hardcoded): {username}")
            resp = jsonify({'msg': 'Login successful', 'redirect': '/dashboard'})
            set_access_cookies(resp, access_token)
            return resp
        
        log_action(f"Failed login attempt (invalid credentials): {username}")
        return jsonify({'msg': 'Неверный логин или пароль'}), 401
    except Exception as e:
        logging.error(f"Login API Error: {str(e)}")
        return jsonify({'msg': f'Ошибка сервера: {str(e)}'}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    resp = jsonify({'msg': 'Logged out'})
    unset_jwt_cookies(resp)
    return resp

@app.route('/config.json')
def get_config():
    return send_from_directory(BASE_DIR, 'config.json')

@app.route('/api/images', methods=['GET'])
@jwt_required()
def get_images():
    images = ImageMetadata.query.order_by(ImageMetadata.priority.desc(), ImageMetadata.upload_date.desc()).all()
    return jsonify([{
        'id': img.id,
        'filename': img.filename,
        'original_name': img.original_name,
        'name': img.name or img.original_name,
        'description': img.description or '',
        'priority': img.priority,
        'url': f'/uploads/images/{img.filename}',
        'preview': f'/uploads/previews/{img.filename}',
        'size': img.size,
        'mimetype': img.mimetype,
        'is_hero': img.is_hero,
        'is_bg': img.is_bg
    } for img in images])

@app.route('/api/upload/image', methods=['POST'])
@jwt_required()
def upload_image():
    if 'file' not in request.files:
        return jsonify({'msg': 'Файл не выбран'}), 400
    
    files = request.files.getlist('file')
    results = []
    
    allowed_formats = ['JPEG', 'PNG', 'WEBP']
    
    for file in files:
        if file.filename == '':
            continue
            
        try:
            # Check format via PIL (XSS Protection/MIME validation)
            img = Image.open(file)
            if img.format not in allowed_formats:
                return jsonify({'msg': f'Формат {img.format} не поддерживается. Только JPEG, PNG, WEBP.'}), 400
                
            # Temporary path to calculate hash
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'], f"temp_{secure_filename(file.filename)}")
            file.seek(0)
            file.save(temp_path)
            
            file_hash = calculate_sha256(temp_path)
            
            # Check if file already exists by hash
            existing_img = ImageMetadata.query.filter_by(hash=file_hash).first()
            if existing_img:
                os.remove(temp_path)
                results.append({
                    'id': existing_img.id,
                    'filename': existing_img.filename,
                    'preview': f'/uploads/previews/{existing_img.filename}',
                    'msg': 'Файл уже существует (дубликат)'
                })
                continue

            # Secure filename and unique ID
            original_filename = secure_filename(file.filename)
            unique_prefix = hashlib.md5(f"{datetime.now()}{original_filename}".encode()).hexdigest()[:8]
            filename = f"{unique_prefix}_{original_filename}"
            
            path = os.path.join(app.config['UPLOAD_FOLDER'], 'images', filename)
            shutil.move(temp_path, path)
            
            # File metadata
            file_size = os.path.getsize(path)
            if file_size > 30 * 1024 * 1024:
                os.remove(path)
                return jsonify({'msg': f'Файл {original_filename} слишком велик (>30MB)'}), 400

            # Optimize and create preview
            img = Image.open(path)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
                
            img.thumbnail((1920, 1920))
            img.save(path, optimize=True, quality=85)
            
            preview_path = os.path.join(app.config['UPLOAD_FOLDER'], 'previews', filename)
            img.thumbnail((400, 400))
            img.save(preview_path)
            
            # Save to DB
            mimetype = img.format.lower() if img.format else 'image/jpeg'
            if mimetype == 'jpeg': mimetype = 'image/jpeg'
            elif mimetype == 'png': mimetype = 'image/png'
            elif mimetype == 'webp': mimetype = 'image/webp'
            
            new_img = ImageMetadata(
                filename=filename,
                original_name=original_filename,
                mimetype=mimetype,
                size=file_size,
                hash=file_hash,
                name=original_filename
            )
            db.session.add(new_img)
            db.session.commit()
            
            log_action(f"Загружено изображение: {filename}")
            results.append({
                'id': new_img.id,
                'filename': filename,
                'preview': f'/uploads/previews/{filename}'
            })
        except Exception as e:
            logging.error(f"Ошибка загрузки файла: {str(e)}")
            if os.path.exists(temp_path): os.remove(temp_path)
            return jsonify({'msg': f'Ошибка при обработке {file.filename}: {str(e)}'}), 500
            
    return jsonify({'msg': f'Успешно загружено {len(results)} файлов', 'files': results})

@app.route('/api/update/image-metadata/<int:image_id>', methods=['POST'])
@jwt_required()
def update_image_metadata(image_id):
    img = ImageMetadata.query.get_or_404(image_id)
    data = request.json
    
    if 'name' in data: img.name = data['name']
    if 'description' in data: img.description = data['description']
    if 'priority' in data: img.priority = int(data.get('priority', 0))
    
    db.session.commit()
    log_action(f"Обновлены метаданные изображения {img.filename}")
    return jsonify({'msg': 'Метаданные обновлены'})

@app.route('/api/delete/image/<int:image_id>', methods=['DELETE'])
@jwt_required()
def delete_image(image_id):
    img_meta = ImageMetadata.query.get_or_404(image_id)
    filename = img_meta.filename
    
    try:
        # Move to trash (30-day backup logic)
        source_path = os.path.join(app.config['UPLOAD_FOLDER'], 'images', filename)
        trash_path = os.path.join(app.config['TRASH_FOLDER'], filename)
        
        if os.path.exists(source_path):
            shutil.move(source_path, trash_path)
            
        # Also remove preview
        preview_path = os.path.join(app.config['UPLOAD_FOLDER'], 'previews', filename)
        if os.path.exists(preview_path):
            os.remove(preview_path)
            
        db.session.delete(img_meta)
        db.session.commit()
        
        log_action(f"Удалено изображение (перемещено в корзину): {filename}")
        return jsonify({'msg': 'Изображение удалено'})
    except Exception as e:
        logging.error(f"Ошибка удаления: {e}")
        return jsonify({'msg': 'Ошибка при удалении'}), 500

@app.route('/api/update/hero', methods=['POST'])
@jwt_required()
def update_hero():
    data = request.json
    img_id = data.get('image_id')
    type = data.get('type') # 'hero' or 'bg'
    
    img = ImageMetadata.query.get_or_404(img_id)
    
    # Reset others
    if type == 'hero':
        ImageMetadata.query.update({ImageMetadata.is_hero: False})
        img.is_hero = True
    else:
        ImageMetadata.query.update({ImageMetadata.is_bg: False})
        img.is_bg = True
        
    db.session.commit()
    
    # Update config.json too
    config_path = update_config_path('config.json')
    with open(config_path, 'r+', encoding='utf-8') as f:
        config = json.load(f)
        if 'placements' not in config: config['placements'] = {}
        config['placements'][type] = f'/uploads/images/{img.filename}'
        f.seek(0)
        json.dump(config, f, indent=4, ensure_ascii=False)
        f.truncate()
        
    log_action(f"Обновлено {type} изображение: {img.filename}")
    return jsonify({'msg': f'Главное изображение {type} обновлено'})

# Update config.json path in functions
def update_config_path(filename):
    return os.path.join(BASE_DIR, filename)

@app.route('/api/update/config', methods=['POST'])
@jwt_required()
def update_config():
    data = request.json
    with open(update_config_path('config.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    log_action("Updated site configuration")
    return jsonify({'msg': 'Configuration updated'})

@app.route('/api/update/software', methods=['POST'])
@jwt_required()
def update_software():
    if 'file' not in request.files:
        return jsonify({'msg': 'Файл не выбран'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'msg': 'Имя файла пустое'}), 400

    original_filename = secure_filename(file.filename)
    
    # Allow ZIP and EXE
    if not (original_filename.lower().endswith('.zip') or original_filename.lower().endswith('.exe')):
        return jsonify({'msg': 'Только ZIP или EXE файлы'}), 400

    # Temporary path for hash check
    temp_path = os.path.join(app.config['UPLOAD_FOLDER'], f"temp_sw_{original_filename}")
    file.save(temp_path)
    
    checksum = calculate_sha256(temp_path)
    
    # Unique filename to avoid collisions but keep original name part
    filename = f"{checksum[:8]}_{original_filename}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'software', filename)

    if os.path.exists(filepath):
        os.remove(temp_path)
        # Still update config if it's the same file but maybe config was changed
    else:
        shutil.move(temp_path, filepath)

    # 1. Backup current config
    config_json_path = update_config_path('config.json')
    if os.path.exists(config_json_path):
        # Always keep the very last stable version for quick rollback
        shutil.copy(config_json_path, os.path.join(app.config['BACKUP_FOLDER'], 'config_last.json'))
        # Also keep a timestamped version for history
        shutil.copy(config_json_path, os.path.join(app.config['BACKUP_FOLDER'], f"config_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"))

    # 2. Update config.json
    try:
        with open(config_json_path, 'r+', encoding='utf-8') as f:
            config = json.load(f)
            
            if filename.lower().endswith('.exe'):
                config['download_url'] = f'/uploads/software/{filename}'
                config['file_size'] = f"{os.path.getsize(filepath) / (1024*1024):.1f} MB"
                log_action(f"EXE Software published: {filename} (SHA256: {checksum[:8]})")
                msg = 'EXE загружен и опубликован'
                
            elif filename.lower().endswith('.zip'):
                with zipfile.ZipFile(filepath, 'r') as zip_ref:
                    if 'update.json' in zip_ref.namelist():
                        update_info = json.loads(zip_ref.read('update.json'))
                        new_version = update_info.get('version', 'unknown')
                        config['version'] = new_version
                        config['download_url'] = f'/uploads/software/{filename}'
                        config['file_size'] = f"{os.path.getsize(filepath) / (1024*1024):.1f} MB"
                        log_action(f"ZIP Software update published: v{new_version}")
                        msg = f'ZIP обновление v{new_version} установлено и опубликовано'
                    else:
                        # If no update.json, just treat as a downloadable zip
                        config['download_url'] = f'/uploads/software/{filename}'
                        config['file_size'] = f"{os.path.getsize(filepath) / (1024*1024):.1f} MB"
                        log_action(f"ZIP Software published (no update.json): {filename}")
                        msg = 'ZIP загружен и опубликован'
            
            f.seek(0)
            json.dump(config, f, indent=4, ensure_ascii=False)
            f.truncate()
            
        return jsonify({'msg': msg, 'hash': checksum, 'url': config['download_url']})
        
    except Exception as e:
        log_action(f"Software update FAILED: {str(e)}")
        return jsonify({'msg': 'Ошибка при публикации', 'log': str(e)}), 500

@app.route('/api/update/rollback', methods=['POST'])
@jwt_required()
def rollback():
    backup = os.path.join(app.config['BACKUP_FOLDER'], 'config_last.json')
    config_json_path = update_config_path('config.json')
    if os.path.exists(backup):
        shutil.copy(backup, config_json_path)
        log_action("Performed software rollback")
        return jsonify({'msg': 'Rollback successful'})
    return jsonify({'msg': 'No backup found'}), 400

@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'js'), filename)

@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'css'), filename)

@app.route('/uploads/<path:filename>')
def serve_uploads(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(port=5000, debug=True)
