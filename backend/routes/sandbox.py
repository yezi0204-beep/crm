"""营销作战电子沙盘路由。

以中国地图形式展示：客户所在城市、销售人员当前位置（由最近拜访推断）、
干系人、拜访概要、商机情况聚合数据。

数据可见性：data.view_all 权限可见全部，普通销售仅见自己名下客户/商机/拜访。
定位数据来源：customers.region / customers.address 内置城市字典解析，
未定位客户可通过 set-city 接口快速补录城市。
"""
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import request, jsonify
from extensions import (get_db, token_required, user_can,
                        record_operation_log)
from . import sandbox_bp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 内置中国主要城市经纬度字典（真实坐标，来源：国家行政区划中心坐标）
# key 为城市简称，value: [经度, 纬度, 省份]
# ---------------------------------------------------------------------------
CITY_COORDS = {
    '北京': [116.40, 39.90, '北京市'], '上海': [121.47, 31.23, '上海市'],
    '天津': [117.20, 39.13, '天津市'], '重庆': [106.55, 29.57, '重庆市'],
    # 河北
    '石家庄': [114.51, 38.04, '河北'], '唐山': [118.18, 39.63, '河北'],
    '秦皇岛': [119.60, 39.94, '河北'], '邯郸': [114.54, 36.63, '河北'],
    '邢台': [114.50, 37.07, '河北'], '保定': [115.48, 38.87, '河北'],
    '张家口': [114.88, 40.82, '河北'], '承德': [117.93, 40.97, '河北'],
    '沧州': [116.84, 38.30, '河北'], '廊坊': [116.68, 39.54, '河北'],
    '衡水': [115.67, 37.74, '河北'],
    # 山西
    '太原': [112.55, 37.87, '山西'], '大同': [113.30, 40.08, '山西'],
    '阳泉': [113.58, 37.86, '山西'], '长治': [113.12, 36.19, '山西'],
    '晋城': [112.85, 35.49, '山西'], '朔州': [112.43, 39.33, '山西'],
    '晋中': [112.75, 37.69, '山西'], '运城': [111.00, 35.03, '山西'],
    '忻州': [112.73, 38.42, '山西'], '临汾': [111.52, 36.09, '山西'],
    '吕梁': [111.14, 37.52, '山西'],
    # 内蒙古
    '呼和浩特': [111.67, 40.82, '内蒙古'], '包头': [109.84, 40.66, '内蒙古'],
    '乌海': [106.79, 39.67, '内蒙古'], '赤峰': [118.89, 42.26, '内蒙古'],
    '通辽': [122.24, 43.66, '内蒙古'], '鄂尔多斯': [109.99, 39.82, '内蒙古'],
    '呼伦贝尔': [119.77, 49.21, '内蒙古'], '巴彦淖尔': [107.42, 40.75, '内蒙古'],
    '乌兰察布': [113.13, 41.00, '内蒙古'],
    # 辽宁
    '沈阳': [123.43, 41.80, '辽宁'], '大连': [121.62, 38.92, '辽宁'],
    '鞍山': [122.99, 41.11, '辽宁'], '抚顺': [123.96, 41.87, '辽宁'],
    '本溪': [123.77, 41.30, '辽宁'], '丹东': [124.38, 40.13, '辽宁'],
    '锦州': [121.14, 41.10, '辽宁'], '营口': [122.24, 40.67, '辽宁'],
    '阜新': [121.67, 42.02, '辽宁'], '辽阳': [123.17, 41.27, '辽宁'],
    '盘锦': [122.07, 41.12, '辽宁'], '铁岭': [123.84, 42.29, '辽宁'],
    '朝阳': [120.45, 41.57, '辽宁'], '葫芦岛': [120.84, 40.71, '辽宁'],
    # 吉林
    '长春': [125.32, 43.90, '吉林'], '吉林': [126.55, 43.84, '吉林'],
    '四平': [124.35, 43.17, '吉林'], '辽源': [125.14, 42.89, '吉林'],
    '通化': [125.94, 41.73, '吉林'], '白山': [126.42, 41.94, '吉林'],
    '松原': [124.83, 45.14, '吉林'], '白城': [122.84, 45.62, '吉林'],
    # 黑龙江
    '哈尔滨': [126.64, 45.76, '黑龙江'], '齐齐哈尔': [123.92, 47.35, '黑龙江'],
    '鸡西': [130.97, 45.30, '黑龙江'], '鹤岗': [130.30, 47.33, '黑龙江'],
    '双鸭山': [131.16, 46.65, '黑龙江'], '大庆': [125.10, 46.59, '黑龙江'],
    '伊春': [128.84, 47.73, '黑龙江'], '佳木斯': [130.32, 46.80, '黑龙江'],
    '七台河': [131.00, 45.77, '黑龙江'], '牡丹江': [129.63, 44.55, '黑龙江'],
    '黑河': [127.53, 50.24, '黑龙江'], '绥化': [126.97, 46.65, '黑龙江'],
    # 江苏
    '南京': [118.78, 32.06, '江苏'], '无锡': [120.31, 31.49, '江苏'],
    '徐州': [117.28, 34.26, '江苏'], '常州': [119.97, 31.81, '江苏'],
    '苏州': [120.62, 31.30, '江苏'], '南通': [120.86, 32.01, '江苏'],
    '连云港': [119.22, 34.60, '江苏'], '淮安': [119.02, 33.61, '江苏'],
    '盐城': [120.14, 33.35, '江苏'], '扬州': [119.42, 32.39, '江苏'],
    '镇江': [119.42, 32.20, '江苏'], '泰州': [119.92, 32.46, '江苏'],
    '宿迁': [118.28, 33.96, '江苏'],
    # 浙江
    '杭州': [120.15, 30.28, '浙江'], '宁波': [121.62, 29.87, '浙江'],
    '温州': [120.70, 28.00, '浙江'], '嘉兴': [120.76, 30.75, '浙江'],
    '湖州': [120.09, 30.87, '浙江'], '绍兴': [120.58, 30.03, '浙江'],
    '金华': [119.65, 29.08, '浙江'], '衢州': [118.87, 28.94, '浙江'],
    '舟山': [122.21, 30.00, '浙江'], '台州': [121.43, 28.66, '浙江'],
    '丽水': [119.92, 28.45, '浙江'],
    # 安徽
    '合肥': [117.28, 31.86, '安徽'], '芜湖': [118.38, 31.33, '安徽'],
    '蚌埠': [117.39, 32.92, '安徽'], '淮南': [116.98, 32.63, '安徽'],
    '马鞍山': [118.51, 31.67, '安徽'], '淮北': [116.80, 33.95, '安徽'],
    '铜陵': [117.81, 30.95, '安徽'], '安庆': [117.05, 30.53, '安徽'],
    '黄山': [118.34, 29.71, '安徽'], '滁州': [118.32, 32.30, '安徽'],
    '阜阳': [115.82, 32.89, '安徽'], '宿州': [116.96, 33.65, '安徽'],
    '六安': [116.51, 31.74, '安徽'], '亳州': [115.78, 33.85, '安徽'],
    '池州': [117.49, 30.66, '安徽'], '宣城': [118.76, 30.94, '安徽'],
    # 福建
    '福州': [119.30, 26.08, '福建'], '厦门': [118.09, 24.48, '福建'],
    '莆田': [119.01, 25.45, '福建'], '三明': [117.64, 26.27, '福建'],
    '泉州': [118.59, 24.91, '福建'], '漳州': [117.65, 24.51, '福建'],
    '南平': [118.18, 26.64, '福建'], '龙岩': [117.02, 25.08, '福建'],
    '宁德': [119.55, 26.66, '福建'],
    # 江西
    '南昌': [115.89, 28.68, '江西'], '景德镇': [117.18, 29.27, '江西'],
    '萍乡': [113.85, 27.62, '江西'], '九江': [116.00, 29.47, '江西'],
    '新余': [114.92, 27.82, '江西'], '鹰潭': [117.07, 28.26, '江西'],
    '赣州': [114.93, 25.85, '江西'], '吉安': [114.99, 27.11, '江西'],
    '宜春': [114.42, 27.81, '江西'], '抚州': [116.36, 27.98, '江西'],
    '上饶': [117.94, 28.45, '江西'],
    # 山东
    '济南': [117.00, 36.65, '山东'], '青岛': [120.38, 36.07, '山东'],
    '淄博': [118.05, 36.78, '山东'], '枣庄': [117.32, 34.81, '山东'],
    '东营': [118.67, 37.43, '山东'], '烟台': [121.39, 37.52, '山东'],
    '潍坊': [119.16, 36.71, '山东'], '济宁': [116.59, 35.41, '山东'],
    '泰安': [117.09, 36.20, '山东'], '威海': [122.12, 37.51, '山东'],
    '日照': [119.53, 35.42, '山东'], '临沂': [118.35, 35.10, '山东'],
    '德州': [116.36, 37.43, '山东'], '聊城': [115.98, 36.45, '山东'],
    '滨州': [117.97, 37.38, '山东'], '菏泽': [115.48, 35.23, '山东'],
    # 河南
    '郑州': [113.63, 34.75, '河南'], '开封': [114.30, 34.80, '河南'],
    '洛阳': [112.45, 34.62, '河南'], '平顶山': [113.19, 33.77, '河南'],
    '安阳': [114.35, 36.10, '河南'], '鹤壁': [114.30, 35.75, '河南'],
    '新乡': [113.93, 35.30, '河南'], '焦作': [113.24, 35.22, '河南'],
    '濮阳': [115.03, 35.76, '河南'], '许昌': [113.85, 34.04, '河南'],
    '漯河': [114.02, 33.58, '河南'], '三门峡': [111.19, 34.77, '河南'],
    '南阳': [112.53, 32.99, '河南'], '商丘': [115.66, 34.41, '河南'],
    '信阳': [114.09, 32.15, '河南'], '周口': [114.65, 33.62, '河南'],
    '驻马店': [114.36, 33.01, '河南'],
    # 湖北
    '武汉': [114.31, 30.52, '湖北'], '黄石': [115.04, 30.20, '湖北'],
    '十堰': [110.80, 32.63, '湖北'], '宜昌': [111.29, 30.69, '湖北'],
    '襄阳': [112.12, 32.01, '湖北'], '鄂州': [114.89, 30.39, '湖北'],
    '荆门': [112.20, 31.04, '湖北'], '孝感': [113.92, 30.93, '湖北'],
    '荆州': [112.24, 30.32, '湖北'], '黄冈': [114.87, 30.45, '湖北'],
    '咸宁': [114.32, 29.84, '湖北'], '随州': [113.38, 31.72, '湖北'],
    '恩施': [109.49, 30.27, '湖北'],
    # 湖南
    '长沙': [112.94, 28.23, '湖南'], '株洲': [113.13, 27.83, '湖南'],
    '湘潭': [112.94, 27.83, '湖南'], '衡阳': [112.57, 26.89, '湖南'],
    '邵阳': [111.47, 27.24, '湖南'], '岳阳': [113.13, 29.36, '湖南'],
    '常德': [111.69, 29.04, '湖南'], '张家界': [110.48, 29.13, '湖南'],
    '益阳': [112.36, 28.55, '湖南'], '郴州': [113.03, 25.79, '湖南'],
    '永州': [111.61, 26.43, '湖南'], '怀化': [110.00, 27.57, '湖南'],
    '娄底': [112.00, 27.70, '湖南'],
    # 广东
    '广州': [113.26, 23.13, '广东'], '韶关': [113.60, 24.81, '广东'],
    '深圳': [114.06, 22.55, '广东'], '珠海': [113.58, 22.27, '广东'],
    '汕头': [116.68, 23.35, '广东'], '佛山': [113.12, 23.02, '广东'],
    '江门': [113.08, 22.58, '广东'], '湛江': [110.36, 21.27, '广东'],
    '茂名': [110.93, 21.66, '广东'], '肇庆': [112.47, 23.05, '广东'],
    '惠州': [114.42, 23.11, '广东'], '梅州': [116.12, 24.29, '广东'],
    '汕尾': [115.37, 22.79, '广东'], '河源': [114.70, 23.74, '广东'],
    '阳江': [111.98, 21.86, '广东'], '清远': [113.06, 23.68, '广东'],
    '东莞': [113.75, 23.05, '广东'], '中山': [113.39, 22.52, '广东'],
    '潮州': [116.63, 23.66, '广东'], '揭阳': [116.37, 23.55, '广东'],
    '云浮': [112.04, 22.92, '广东'],
    # 广西
    '南宁': [108.32, 22.82, '广西'], '柳州': [109.42, 24.33, '广西'],
    '桂林': [110.29, 25.27, '广西'], '梧州': [111.28, 23.48, '广西'],
    '北海': [109.12, 21.48, '广西'], '防城港': [108.35, 21.69, '广西'],
    '钦州': [108.62, 21.96, '广西'], '贵港': [109.60, 23.11, '广西'],
    '玉林': [110.18, 22.65, '广西'], '百色': [106.62, 23.90, '广西'],
    '贺州': [111.57, 24.40, '广西'], '河池': [108.06, 24.70, '广西'],
    '来宾': [109.23, 23.73, '广西'], '崇左': [107.36, 22.38, '广西'],
    # 海南
    '海口': [110.20, 20.04, '海南'], '三亚': [109.51, 18.25, '海南'],
    # 四川
    '成都': [104.07, 30.57, '四川'], '自贡': [104.78, 29.34, '四川'],
    '攀枝花': [101.72, 26.58, '四川'], '泸州': [105.44, 28.87, '四川'],
    '德阳': [104.40, 31.13, '四川'], '绵阳': [104.68, 31.47, '四川'],
    '广元': [105.84, 32.43, '四川'], '遂宁': [105.57, 30.51, '四川'],
    '内江': [105.06, 29.58, '四川'], '乐山': [103.77, 29.55, '四川'],
    '南充': [106.11, 30.84, '四川'], '眉山': [103.83, 30.05, '四川'],
    '宜宾': [104.64, 28.75, '四川'], '广安': [106.63, 30.47, '四川'],
    '达州': [107.47, 31.21, '四川'], '雅安': [103.00, 29.98, '四川'],
    '巴中': [106.75, 31.87, '四川'], '资阳': [104.64, 30.13, '四川'],
    # 贵州
    '贵阳': [106.63, 26.65, '贵州'], '六盘水': [104.83, 26.60, '贵州'],
    '遵义': [106.93, 27.73, '贵州'], '安顺': [105.93, 26.25, '贵州'],
    '毕节': [105.28, 27.30, '贵州'], '铜仁': [109.19, 27.73, '贵州'],
    # 云南
    '昆明': [102.83, 24.88, '云南'], '曲靖': [103.80, 25.49, '云南'],
    '玉溪': [102.55, 24.35, '云南'], '保山': [99.17, 25.12, '云南'],
    '昭通': [103.72, 27.34, '云南'], '丽江': [100.23, 26.86, '云南'],
    '普洱': [100.97, 22.79, '云南'], '临沧': [100.09, 23.88, '云南'],
    # 西藏
    '拉萨': [91.11, 29.66, '西藏'], '日喀则': [88.88, 29.27, '西藏'],
    # 陕西
    '西安': [108.94, 34.34, '陕西'], '铜川': [108.95, 34.90, '陕西'],
    '宝鸡': [107.24, 34.36, '陕西'], '咸阳': [108.71, 34.33, '陕西'],
    '渭南': [109.51, 34.50, '陕西'], '延安': [109.49, 36.59, '陕西'],
    '汉中': [107.02, 33.07, '陕西'], '榆林': [109.73, 38.28, '陕西'],
    '安康': [109.03, 32.68, '陕西'], '商洛': [109.94, 33.87, '陕西'],
    # 甘肃
    '兰州': [103.83, 36.06, '甘肃'], '嘉峪关': [98.28, 39.77, '甘肃'],
    '金昌': [102.19, 38.52, '甘肃'], '白银': [104.14, 36.55, '甘肃'],
    '天水': [105.72, 34.58, '甘肃'], '武威': [102.64, 37.93, '甘肃'],
    '张掖': [100.45, 38.93, '甘肃'], '平凉': [106.68, 35.54, '甘肃'],
    '酒泉': [98.49, 39.73, '甘肃'], '庆阳': [107.64, 35.71, '甘肃'],
    # 青海/宁夏/新疆
    '西宁': [101.78, 36.62, '青海'], '海东': [102.10, 36.50, '青海'],
    '银川': [106.23, 38.49, '宁夏'], '石嘴山': [106.38, 39.02, '宁夏'],
    '吴忠': [106.20, 37.99, '宁夏'], '固原': [106.24, 36.00, '宁夏'],
    '中卫': [105.20, 37.51, '宁夏'],
    '乌鲁木齐': [87.62, 43.83, '新疆'], '克拉玛依': [84.89, 45.58, '新疆'],
    '吐鲁番': [89.19, 42.95, '新疆'], '哈密': [93.51, 42.82, '新疆'],
    # 港澳台
    '香港': [114.17, 22.32, '港澳'], '澳门': [113.55, 22.20, '港澳'],
    '台北': [121.52, 25.03, '台湾'],
}


def resolve_city(*texts):
    """从多个文本字段中解析城市，返回 (city_name, coord) 或 (None, None)。"""
    for text in texts:
        if not text:
            continue
        t = str(text).strip()
        if not t:
            continue
        # 优先精确匹配城市名
        for city, coord in CITY_COORDS.items():
            if city in t:
                return city, coord
    return None, None


def register_routes(app):
    app.register_blueprint(sandbox_bp, url_prefix='/api/sandbox')


@sandbox_bp.route('/data', methods=['GET'])
@token_required
def get_sandbox_data():
    """沙盘聚合数据：客户定位、干系人、拜访概要、商机情况、销售人员位置。"""
    username = request.current_user['username']
    can_view_all = user_can(username, 'data.view_all')
    db = get_db()

    # 1. 客户 + 负责人
    cust_sql = """
        SELECT c.id, c.name, c.region, c.address, c.level, c.industry,
               c.owner_id, c.contact_name, u.name AS owner_name
        FROM customers c LEFT JOIN users u ON c.owner_id = u.username
    """
    params = []
    if not can_view_all:
        cust_sql += " WHERE c.owner_id = ?"
        params.append(username)
    customers = [dict(r) for r in db.execute(cust_sql, params).fetchall()]
    cust_map = {c['id']: c for c in customers}

    # 2. 商机（按客户聚合）
    biz_sql = """
        SELECT b.id, b.cust_id, b.title, b.amount, b.stage, b.status,
               b.stakeholder, b.owner_id, b.predict_date, u.name AS owner_name
        FROM business b LEFT JOIN users u ON b.owner_id = u.username
    """
    biz_params = []
    if not can_view_all:
        biz_sql += " WHERE b.owner_id = ?"
        biz_params.append(username)
    businesses = [dict(r) for r in db.execute(biz_sql, biz_params).fetchall()]

    biz_by_cust = defaultdict(list)
    for b in businesses:
        biz_by_cust[b['cust_id']].append(b)

    # 3. 拜访（仅拜访类，且关联客户）
    visit_sql = """
        SELECT v.id, v.cust_id, v.visitor_id, v.plan_date, v.actual_date,
               v.status, v.purpose, v.result, v.contact_person, v.work_type,
               u.name AS visitor_name
        FROM visits v LEFT JOIN users u ON v.visitor_id = u.username
        WHERE v.cust_id IS NOT NULL AND v.work_type = 'visit'
    """
    visit_params = []
    if not can_view_all:
        visit_sql += " AND v.visitor_id = ?"
        visit_params.append(username)
    visits = [dict(r) for r in db.execute(visit_sql, visit_params).fetchall()]

    visits_by_cust = defaultdict(list)
    for v in visits:
        visits_by_cust[v['cust_id']].append(v)
    for k in visits_by_cust:
        visits_by_cust[k].sort(
            key=lambda x: (x['plan_date'] or '', x['id'] or 0), reverse=True)

    # 4. 组装客户数据（含定位、干系人、商机、拜访）
    located, unlocated = [], []
    stage_order = ['初步洽谈', '方案报价', '商务谈判', '销售实现']
    for c in customers:
        cid = c['id']
        city, coord = resolve_city(c['region'], c['address'])
        c_biz_all = biz_by_cust.get(cid, [])
        c_biz_active = [b for b in c_biz_all if b['status'] == 'active']
        biz_amount = round(sum(b['amount'] or 0 for b in c_biz_active), 2)

        # 干系人：客户联系人 + 在途商机干系人 + 近期拜访联系人
        stakeholders = []
        if c.get('contact_name'):
            stakeholders.append({'name': c['contact_name'], 'source': '客户联系人'})
        seen = {c.get('contact_name')}
        for b in c_biz_active:
            if b.get('stakeholder') and b['stakeholder'] not in seen:
                stakeholders.append({'name': b['stakeholder'], 'source': '商机干系人'})
                seen.add(b['stakeholder'])
        for v in visits_by_cust.get(cid, [])[:5]:
            if v.get('contact_person') and v['contact_person'] not in seen:
                stakeholders.append({'name': v['contact_person'], 'source': '拜访接触'})
                seen.add(v['contact_person'])

        # 商机阶段分布
        stage_dist = defaultdict(int)
        for b in c_biz_active:
            for s in stage_order:
                if s in (b['stage'] or ''):
                    stage_dist[s] += 1
                    break

        c_visits = visits_by_cust.get(cid, [])[:6]
        visit_briefs = [{
            'plan_date': v['plan_date'],
            'status': v['status'],
            'purpose': v['purpose'] or '',
            'visitor_name': v['visitor_name'] or v['visitor_id'],
            'contact_person': v['contact_person'] or '',
        } for v in c_visits]

        item = {
            'id': cid,
            'name': c['name'],
            'region': c['region'] or '',
            'address': c['address'] or '',
            'level': c['level'] or '',
            'industry': c['industry'] or '',
            'owner_id': c['owner_id'],
            'owner_name': c['owner_name'] or c['owner_id'],
            'city': city,
            'lng': coord[0] if coord else None,
            'lat': coord[1] if coord else None,
            'province': coord[2] if coord else '',
            'biz_count': len(c_biz_active),
            'biz_amount': biz_amount,
            'biz_stages': dict(stage_dist),
            'biz_list': [{
                'id': b['id'], 'title': b['title'], 'amount': b['amount'] or 0,
                'stage': b['stage'] or '', 'status': b['status'],
                'stakeholder': b['stakeholder'] or '',
            } for b in sorted(c_biz_active, key=lambda x: -(x['amount'] or 0))[:8]],
            'stakeholders': stakeholders,
            'visits': visit_briefs,
            'last_visit': visit_briefs[0]['plan_date'] if visit_briefs else None,
            'visit_count': len(visits_by_cust.get(cid, [])),
        }
        (located if city else unlocated).append(item)

    located.sort(key=lambda x: -x['biz_amount'])
    unlocated.sort(key=lambda x: -x['biz_amount'])

    # 5. 销售人员当前位置（由最近一次定位到城市的拜访推断）
    user_sql = """SELECT username, name, role, department FROM users
                  WHERE status = '在职' AND role IN ('销售', '主任', '院长')"""
    sales_users = [dict(r) for r in db.execute(user_sql).fetchall()]
    if not can_view_all:
        sales_users = [u for u in sales_users if u['username'] == username]

    cust_stats = defaultdict(lambda: {'cust': 0, 'biz': 0, 'amount': 0.0})
    for c in located + unlocated:
        s = cust_stats[c['owner_id']]
        s['cust'] += 1
        s['biz'] += c['biz_count']
        s['amount'] += c['biz_amount']

    salesmen = []
    for u in sales_users:
        uid = u['username']
        pos = None
        for v in sorted(
                [v for v in visits if v['visitor_id'] == uid],
                key=lambda x: (x['plan_date'] or '', x['id'] or 0), reverse=True):
            cust = cust_map.get(v['cust_id'])
            if not cust:
                continue
            city, coord = resolve_city(cust['region'], cust['address'])
            if city:
                pos = {'city': city, 'lng': coord[0], 'lat': coord[1],
                       'from_customer': cust['name'],
                       'visit_date': v['plan_date']}
                break
        st = cust_stats.get(uid, {'cust': 0, 'biz': 0, 'amount': 0.0})
        salesmen.append({
            'username': uid, 'name': u['name'], 'role': u['role'],
            'department': u['department'],
            'position': pos,
            'customer_count': st['cust'],
            'biz_count': st['biz'],
            'biz_amount': round(st['amount'], 2),
        })
    salesmen.sort(key=lambda x: -x['biz_amount'])

    # 6. 汇总指标（本周拜访按周一为起点）
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    week_start, week_end = monday.isoformat(), (monday + timedelta(days=6)).isoformat()
    week_visits = [v for v in visits
                   if v['plan_date'] and week_start <= v['plan_date'][:10] <= week_end]

    total_biz = sum(c['biz_count'] for c in located + unlocated)
    total_amount = round(sum(c['biz_amount'] for c in located + unlocated), 2)

    return jsonify({
        'code': 200,
        'data': {
            'customers': located,
            'unlocated': unlocated,
            'salesmen': salesmen,
            'summary': {
                'customer_total': len(customers),
                'located_total': len(located),
                'unlocated_total': len(unlocated),
                'biz_total': total_biz,
                'biz_amount': total_amount,
                'week_visit_total': len(week_visits),
                'salesman_total': len(salesmen),
            },
        }
    })


@sandbox_bp.route('/customer-city', methods=['POST'])
@token_required
def set_customer_city():
    """客户城市快速补录：更新 customers.region 字段，用于沙盘定位。"""
    username = request.current_user['username']
    db = get_db()
    data = request.get_json(silent=True) or {}
    cust_id = data.get('cust_id')
    city = (data.get('city') or '').strip()
    if not cust_id or not city:
        return jsonify({'code': 400, 'message': '缺少客户ID或城市', 'data': None}), 400
    if city not in CITY_COORDS:
        return jsonify({'code': 400, 'message': f'暂不支持城市「{city}」，请从下拉列表选择', 'data': None}), 400

    row = db.execute("SELECT owner_id, name FROM customers WHERE id=?",
                     (cust_id,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '客户不存在', 'data': None}), 404
    if not user_can(username, 'data.view_all') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '无权限修改该客户定位', 'data': None}), 403

    coord = CITY_COORDS[city]
    region_val = f"{coord[2]}{city}"
    db.execute("UPDATE customers SET region=? WHERE id=?", (region_val, cust_id))
    db.commit()

    record_operation_log(username, '更新客户定位',
                         '营销作战沙盘',
                         f"客户[{row['name']}] 定位城市: {region_val}")

    return jsonify({
        'code': 200,
        'data': {'ok': True, 'city': city,
                 'lng': coord[0], 'lat': coord[1], 'region': region_val}
    })


@sandbox_bp.route('/cities', methods=['GET'])
@token_required
def get_city_list():
    """可用城市列表（按省份分组），供前端定位下拉使用。"""
    by_prov = defaultdict(list)
    for city, coord in CITY_COORDS.items():
        by_prov[coord[2]].append(city)
    return jsonify({'code': 200,
                    'data': {prov: sorted(cities) for prov, cities in sorted(by_prov.items())}})
