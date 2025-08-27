import warnings
import folium
from flask import Flask, request, render_template_string
import json
import os
import logging
from logging.handlers import RotatingFileHandler
from waitress import serve
import socket

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

# 文件日志
file_handler = RotatingFileHandler(
    'logs/app.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)

# 控制台日志
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
    {"name": "深圳世界之窗", "location": [
        22.5362, 113.9715], "type": "主题公园", "description": "微缩世界著名景观"},
    {"name": "顺德美食街", "location": [22.8407, 113.2384],
        "type": "餐饮", "description": "品尝正宗顺德菜的好去处"},
    {"name": "中山纪念堂", "location": [23.1315, 113.2644],
        "type": "历史建筑", "description": "纪念孙中山先生的宏伟建筑"},
    {"name": "澳门官也街", "location": [22.1547, 113.5560],
        "type": "餐饮", "description": "澳门著名美食街"},
    {"name": "开平碉楼", "location": [22.3764, 112.5707],
        "type": "历史建筑", "description": "世界文化遗产，中西合璧的民居建筑"}
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
            tiles='OpenStreetMap',
            attr='© OpenStreetMap contributors'
        )

        # 添加标记
        for loc in locations:
            icon_config = {
                "历史遗迹": {"color": "red", "icon": "flag"},
                "历史建筑": {"color": "darkred", "icon": "home"},
                "观景台": {"color": "blue", "icon": "eye-open"},
                "主题公园": {"color": "green", "icon": "tree-conifer"},
                "餐饮": {"color": "orange", "icon": "cutlery"},
                "自然风光": {"color": "lightgreen", "icon": "picture"},
                "博物馆": {"color": "purple", "icon": "book"},
                "其他": {"color": "gray", "icon": "info-sign"}
            }

            config = icon_config.get(loc["type"], icon_config["其他"])

            folium.Marker(
                location=loc["location"],
                popup=f"<b>{loc['name']}</b><br>类型: {loc['type']}<br>描述: {loc['description']}",
                tooltip=loc["name"],
                icon=folium.Icon(color=config["color"], icon=config["icon"])
            ).add_to(m)

        # 添加点击获取坐标的功能
        m.add_child(folium.LatLngPopup())

        return render_template_string(HTML_TEMPLATE, map_html=m._repr_html_())

    except Exception as e:
        app.logger.error(f"地图生成错误: {e}")
        return render_template_string(HTML_TEMPLATE.replace('{{ map_html | safe }}', '<div style="padding: 2rem;"><h2>地图加载失败</h2><p>请刷新页面重试</p></div>'))


@app.route('/add_location', methods=['POST'])
def add_location():
    """添加新景点"""
    try:
        name = request.form.get('name', '').strip()
        lat_str = request.form.get('lat', '').strip()
        lng_str = request.form.get('lng', '').strip()
        location_type = request.form.get('type', '').strip()
        description = request.form.get('description', '').strip()

        # 验证输入
        if not all([name, lat_str, lng_str, location_type]):
            return render_template_string(HTML_TEMPLATE.replace('{{ map_html | safe }}', '<div style="padding: 2rem;"><h2>请填写完整信息</h2></div>'),
                                          message="错误：请填写所有必填字段", message_type="error")

        try:
            lat = float(lat_str)
            lng = float(lng_str)
        except ValueError:
            return render_template_string(HTML_TEMPLATE.replace('{{ map_html | safe }}', '<div style="padding: 2rem;"><h2>坐标格式错误</h2></div>'),
                                          message="错误：请输入有效的经纬度坐标", message_type="error")

        # 验证坐标范围
        if not (20 <= lat <= 25 and 110 <= lng <= 117):
            return render_template_string(HTML_TEMPLATE.replace('{{ map_html | safe }}', '<div style="padding: 2rem;"><h2>坐标超出范围</h2></div>'),
                                          message="错误：坐标不在广东/澳门范围内", message_type="error")

        new_location = {
            "name": name,
            "location": [lat, lng],
            "type": location_type,
            "description": description
        }

        locations = load_locations()
        locations.append(new_location)
        save_locations(locations)

        app.logger.info(f"新景点添加成功: {name}")

        # 重定向回主页
        return '''<script>alert("景点添加成功！"); window.location.href = "/";</script>'''

    except Exception as e:
        app.logger.error(f"添加景点错误: {e}")
        return render_template_string(HTML_TEMPLATE.replace('{{ map_html | safe }}', '<div style="padding: 2rem;"><h2>添加失败</h2></div>'),
                                      message=f"错误: {str(e)}", message_type="error")


@app.errorhandler(404)
def not_found_error(error):
    return render_template_string(HTML_TEMPLATE.replace('{{ map_html | safe }}', '<div style="padding: 2rem;"><h2>页面未找到</h2></div>'),
                                  message="页面不存在", message_type="error"), 404


@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"服务器错误: {error}")
    return render_template_string(HTML_TEMPLATE.replace('{{ map_html | safe }}', '<div style="padding: 2rem;"><h2>服务器错误</h2></div>'),
                                  message="服务器内部错误，请稍后重试", message_type="error"), 500


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
        app.logger.info("初始化位置数据文件")

    # 生产环境配置
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')

    local_ip = get_local_ip()

    app.logger.info("=" * 50)
    app.logger.info("🚀 澳门广东景点地图应用启动成功！")
    app.logger.info(f"📊 已加载 {len(load_locations())} 个景点")
    app.logger.info(f"🌐 本地访问: http://127.0.0.1:{port}")
    app.logger.info(f"🌐 网络访问: http://{local_ip}:{port}")
    app.logger.info("🛡️  使用 Waitress 生产服务器")
    app.logger.info("=" * 50)

    # 使用Waitress生产服务器
    serve(app, host=host, port=port, threads=4)
