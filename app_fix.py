import warnings
import folium
from flask import Flask, request, render_template_string
import json
import os
import logging
from logging.handlers import RotatingFileHandler
from waitress import serve
import socket
import random

# 创建Flask应用
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get(
    'SECRET_KEY', 'your-production-secret-key-change-this')
app.config['DEBUG'] = False

# 禁用Flask开发服务器警告
warnings.filterwarnings("ignore", message=".*development server.*")

# 设置日志
if not os.path.exists('logs'):
    os.makedirs('logs')

file_handler = RotatingFileHandler(
    'logs/app.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

app.logger.addHandler(file_handler)
app.logger.addHandler(console_handler)
app.logger.setLevel(logging.INFO)

# 地图初始中心点
INITIAL_CENTER = [22.5, 113.5]
INITIAL_ZOOM = 9

# 预设景点数据
PRESET_LOCATIONS = [
    {"name": "澳门大三巴牌坊", "location": [
        22.1975, 113.5419], "type": "历史遗迹", "description": "澳门最著名的历史遗迹之一"},
    {"name": "澳门旅游塔", "location": [22.1789, 113.5439],
        "type": "观景台", "description": "338米高的观光塔，可蹦极"},
    {"name": "广州塔", "location": [23.1064, 113.3245],
        "type": "观景台", "description": "广州地标建筑，昵称小蛮腰"},
    {"name": "珠海长隆海洋王国", "location": [
        22.1416, 113.5564], "type": "主题公园", "description": "大型海洋主题公园"},
]

# 数据文件路径
DATA_FILE = "locations.json"


def load_locations():
    """从文件加载景点数据"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return PRESET_LOCATIONS
    except Exception as e:
        app.logger.error(f"加载位置数据错误: {e}")
        return PRESET_LOCATIONS


def save_locations(locations):
    """保存景点数据到文件"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(locations, f, ensure_ascii=False, indent=4)
        app.logger.info("位置数据保存成功")
    except Exception as e:
        app.logger.error(f"保存位置数据错误: {e}")


def is_port_available(port):
    """检查端口是否可用"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.bind(('127.0.0.1', port))
            return True
    except socket.error:
        return False


def find_available_port(start_port=5000, max_attempts=100):
    """查找可用的端口"""
    for port in range(start_port, start_port + max_attempts):
        if is_port_available(port):
            return port
    return None


# HTML模板
HTML_TEMPLATE = '''<!DOCTYPE html>
<html>
<head>
    <title>澳门与广东旅游景点地图</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Arial', sans-serif; background: #f0f2f5; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem; text-align: center; }
        .header h1 { margin-bottom: 0.5rem; }
        .container { display: flex; flex-direction: column; height: calc(100vh - 80px); }
        @media (min-width: 768px) { .container { flex-direction: row; } }
        .map-container { flex: 1; min-height: 400px; }
        .sidebar { background: white; padding: 1.5rem; box-shadow: -2px 0 10px rgba(0,0,0,0.1); width: 100%; }
        @media (min-width: 768px) { .sidebar { width: 400px; } }
        .form-group { margin-bottom: 1rem; }
        label { display: block; margin-bottom: 0.5rem; font-weight: 600; color: #333; }
        input, select, textarea { width: 100%; padding: 0.75rem; border: 2px solid #e1e5e9; border-radius: 8px; font-size: 14px; }
        input:focus, select:focus, textarea:focus { outline: none; border-color: #667eea; }
        button { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; padding: 1rem; border-radius: 8px; cursor: pointer; width: 100%; font-size: 16px; font-weight: 600; }
        button:hover { opacity: 0.9; }
        .message { padding: 1rem; border-radius: 8px; margin-top: 1rem; }
        .success { color: #28a745; background: #d4edda; border: 1px solid #c3e6cb; }
        .error { color: #dc3545; background: #f8d7da; border: 1px solid #f5c6cb; }
        .info { color: #17a2b8; background: #d1ecf1; border: 1px solid #bee5eb; }
    </style>
</head>
<body>
    <div class="header">
        <h1>澳门与广东旅游景点地图</h1>
        <p>探索发现粤港澳大湾区的美丽景点</p>
    </div>
    
    <div class="container">
        <div class="map-container" id="map-container">
            {{ map_html | safe }}
        </div>
        
        <div class="sidebar">
            <h2>🗺️ 添加新景点</h2>
            <form action="/add_location" method="post" onsubmit="return validateForm()">
                <div class="form-group">
                    <label for="name">🏷️ 景点名称:</label>
                    <input type="text" id="name" name="name" required placeholder="请输入景点名称">
                </div>
                
                <div class="form-group">
                    <label for="lat">📍 纬度:</label>
                    <input type="number" id="lat" name="lat" step="any" required placeholder="例如：22.1975">
                </div>
                
                <div class="form-group">
                    <label for="lng">📍 经度:</label>
                    <input type="number" id="lng" name="lng" step="any" required placeholder="例如：113.5419">
                </div>
                
                <div class="form-group">
                    <label for="type">🎯 类型:</label>
                    <select id="type" name="type" required>
                        <option value="">请选择类型</option>
                        <option value="历史遗迹">🏛️ 历史遗迹</option>
                        <option value="历史建筑">🏯 历史建筑</option>
                        <option value="观景台">🌄 观景台</option>
                        <option value="主题公园">🎢 主题公园</option>
                        <option value="餐饮">🍜 餐饮</option>
                        <option value="自然风光">🏞️ 自然风光</option>
                        <option value="博物馆">🏛️ 博物馆</option>
                        <option value="其他">🔶 其他</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label for="description">📝 描述:</label>
                    <textarea id="description" name="description" rows="3" placeholder="请输入景点描述..."></textarea>
                </div>
                
                <button type="submit">✅ 添加景点</button>
            </form>
            
            <div class="message info">
                <strong>💡 使用提示:</strong>
                <p>1. 在地图上点击可以获取坐标</p>
                <p>2. 点击标记可以查看景点详情</p>
                <p>3. 拖动地图可以探索不同区域</p>
            </div>
            
            {% if message %}
            <div class="message {{ message_type }}">
                {{ message }}
            </div>
            {% endif %}
        </div>
    </div>

    <script>
        function validateForm() {
            const lat = parseFloat(document.getElementById('lat').value);
            const lng = parseFloat(document.getElementById('lng').value);
            
            if (lat < 20 || lat > 25 || lng < 110 || lng > 117) {
                alert('请输入有效的澳门/广东地区坐标（纬度20-25，经度110-117）');
                return false;
            }
            return true;
        }
        
        document.addEventListener('DOMContentLoaded', function() {
            document.getElementById('name').focus();
        });
    </script>
</body>
</html>'''


@app.route('/')
def index():
    """主页面"""
    try:
        locations = load_locations()

        # 创建地图
        m = folium.Map(
            location=INITIAL_CENTER,
            zoom_start=INITIAL_ZOOM,
            tiles='OpenStreetMap'
        )

        # 添加标记
        for loc in locations:
            if loc["type"] == "历史遗迹":
                icon_color = "red"
            elif loc["type"] == "观景台":
                icon_color = "blue"
            elif loc["type"] == "主题公园":
                icon_color = "green"
            elif loc["type"] == "餐饮":
                icon_color = "orange"
            else:
                icon_color = "gray"

            folium.Marker(
                location=loc["location"],
                popup=f"<b>{loc['name']}</b><br>类型: {loc['type']}<br>描述: {loc['description']}",
                tooltip=loc["name"],
                icon=folium.Icon(color=icon_color, icon="info-sign")
            ).add_to(m)

        m.add_child(folium.LatLngPopup())

        return render_template_string(HTML_TEMPLATE, map_html=m._repr_html_())

    except Exception as e:
        return f"地图加载错误: {str(e)}"


@app.route('/add_location', methods=['POST'])
def add_location():
    """添加新景点"""
    try:
        name = request.form.get('name', '').strip()
        lat = float(request.form.get('lat', '0'))
        lng = float(request.form.get('lng', '0'))
        location_type = request.form.get('type', '').strip()
        description = request.form.get('description', '').strip()

        new_location = {
            "name": name,
            "location": [lat, lng],
            "type": location_type,
            "description": description
        }

        locations = load_locations()
        locations.append(new_location)
        save_locations(locations)

        return '''<script>alert("景点添加成功！"); window.location.href = "/";</script>'''

    except Exception as e:
        return f"添加错误: {str(e)}"


def get_local_ip():
    """获取本地IP地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


if __name__ == '__main__':
    # 确保数据文件存在
    if not os.path.exists(DATA_FILE):
        save_locations(PRESET_LOCATIONS)

    # 查找可用端口
    port = find_available_port(5000)
    if port is None:
        port = random.randint(8000, 9000)
        app.logger.warning(f"使用随机端口: {port}")

    host = '0.0.0.0'
    local_ip = get_local_ip()

    app.logger.info("=" * 50)
    app.logger.info("🚀 澳门广东景点地图应用启动")
    app.logger.info(f"📊 已加载 {len(load_locations())} 个景点")
    app.logger.info(f"🌐 本地访问: http://127.0.0.1:{port}")
    app.logger.info(f"🌐 网络访问: http://{local_ip}:{port}")
    app.logger.info("🛡️  使用 Waitress 生产服务器")
    app.logger.info("=" * 50)

    try:
        # 使用Waitress生产服务器
        serve(app, host=host, port=port, threads=2)
    except OSError as e:
        app.logger.error(f"端口 {port} 被占用，尝试其他端口")
        # 尝试其他端口
        alt_port = find_available_port(8080)
        if alt_port:
            app.logger.info(f"尝试端口: {alt_port}")
            serve(app, host=host, port=alt_port, threads=2)
        else:
            app.logger.error("找不到可用端口，请检查系统")
