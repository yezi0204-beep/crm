"""验证知识图谱实体构建优化效果：
1. 后处理清洗：过滤停用词、代词、通用词、短实体
2. 后处理去重：同名实体只保留一个
3. 关系清洗：源/目标必须都在实体集中、排除自环
4. 规则降级方案：不提取"系统""平台"等无意义通用词
"""
import sys, os
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
sys.path.insert(0, BACKEND_DIR)

from routes.knowledge_graph import (
    _postprocess_extraction, _rule_based_extraction,
    _is_valid_entity_name, _normalize_entity_name
)

print('=== 1. 实体名称校验 ===')
# 停用词应被过滤
assert not _is_valid_entity_name('系统'), '停用词"系统"应被过滤'
assert not _is_valid_entity_name('平台'), '停用词"平台"应被过滤'
assert not _is_valid_entity_name('该公司'), '代词"该公司"应被过滤'
assert not _is_valid_entity_name('我们'), '代词"我们"应被过滤'
assert not _is_valid_entity_name('合同'), '通用词"合同"应被过滤'
assert not _is_valid_entity_name('A'), '单字符应被过滤'
assert not _is_valid_entity_name(''), '空字符串应被过滤'
assert not _is_valid_entity_name('123'), '纯数字应被过滤'
# 有效实体应通过
assert _is_valid_entity_name('华为公司'), '"华为公司"应有效'
assert _is_valid_entity_name('张伟'), '"张伟"应有效'
assert _is_valid_entity_name('雷达模拟器系统'), '"雷达模拟器系统"应有效'
assert _is_valid_entity_name('武器装备科研生产许可证'), '资质名称应有效'
print('  ✓ 停用词/代词/通用词/短实体被正确过滤')

print('\n=== 2. 名称归一化 ===')
assert _normalize_entity_name('  华为公司  ') == '华为公司', '应去除首尾空白'
assert _normalize_entity_name('"张伟"') == '张伟', '应去除引号'
assert _normalize_entity_name('（华为）') == '华为', '应去除中文括号'
assert _normalize_entity_name('(华为)') == '华为', '应去除英文括号'
print('  ✓ 空白/引号/括号被正确归一化')

print('\n=== 3. 后处理：过滤无效实体 + 去重 ===')
# 模拟LLM返回的脏数据
raw = {
    'entities': [
        {'name': '张伟', 'type': 'person', 'description': '销售人员'},
        {'name': '张伟', 'type': 'person', 'description': '应用中心销售经理，负责XX客户'},  # 重复，desc更长应替换
        {'name': '系统', 'type': 'product', 'description': '通用词'},  # 停用词，应过滤
        {'name': '该公司', 'type': 'organization', 'description': '代词'},  # 代词，应过滤
        {'name': '华为科技有限公司', 'type': 'organization', 'description': '客户公司'},
        {'name': '雷达模拟器系统', 'type': 'product', 'description': 'XX型号雷达模拟器'},
        {'name': 'A', 'type': 'person', 'description': '太短'},  # 单字符，应过滤
        {'name': 'invalid_type_entity', 'type': 'nonexistent_type', 'description': '无效类型'},  # 类型归other
        {'name': '北京', 'type': 'location', 'description': '地点'},
    ],
    'relations': [
        {'source': '张伟', 'target': '华为科技有限公司', 'type': 'visits', 'description': '张伟拜访华为'},
        {'source': '张伟', 'target': '张伟', 'type': 'other', 'description': '自环应排除'},  # 自环，应排除
        {'source': '张伟', 'target': '不存在的实体', 'type': 'visits', 'description': '目标不存在'},  # 应排除
        {'source': '系统', 'target': '华为科技有限公司', 'type': 'uses', 'description': '源被过滤'},  # 源被过滤，应排除
        {'source': '张伟', 'target': '华为科技有限公司', 'type': 'visits', 'description': '重复关系'},  # 重复，应排除
        {'source': '华为科技有限公司', 'target': '雷达模拟器系统', 'type': 'invalid_rel_type', 'description': '无效关系类型归related_to'},
    ]
}
result = _postprocess_extraction(raw)
entities = result['entities']
relations = result['relations']

# 实体数量：张伟 + 华为 + 雷达模拟器系统 + invalid_type_entity(other) + 北京 = 5
assert len(entities) == 5, f'实体数量错误：{len(entities)}，期望5。实体：{[e["name"] for e in entities]}'
# 停用词被过滤
entity_names = [e['name'] for e in entities]
assert '系统' not in entity_names, '"系统"应被过滤'
assert '该公司' not in entity_names, '"该公司"应被过滤'
assert 'A' not in entity_names, '"A"应被过滤'
# 去重：张伟只有一个
zhang_wei = [e for e in entities if e['name'] == '张伟']
assert len(zhang_wei) == 1, f'张伟应只有一个，实际{len(zhang_wei)}'
# desc更长的被保留
assert '负责XX客户' in zhang_wei[0]['description'], f'应保留更长描述：{zhang_wei[0]["description"]}'
# 无效类型归other
inv = [e for e in entities if e['name'] == 'invalid_type_entity'][0]
assert inv['type'] == 'other', f'无效类型应归other：{inv["type"]}'
print(f'  ✓ 过滤后实体数={len(entities)}（原9个→5个），停用词/代词/短实体/重复已清除')
print(f'    实体: {[(e["name"], e["type"]) for e in entities]}')

# 关系数量：张伟→华为(visits) + 华为→雷达(related_to) = 2
assert len(relations) == 2, f'关系数量错误：{len(relations)}，期望2。关系：{[(r["source"],r["target"],r["type"]) for r in relations]}'
# 自环被排除
assert not any(r['source'] == r['target'] for r in relations), '自环应被排除'
# 不存在的实体关系被排除
assert not any(r['target'] == '不存在的实体' for r in relations), '目标不存在的应被排除'
# 重复关系被排除
visits_count = sum(1 for r in relations if r['type'] == 'visits')
assert visits_count == 1, f'visits关系应只有1个，实际{visits_count}'
# 无效关系类型归related_to
rel_radar = [r for r in relations if r['target'] == '雷达模拟器系统'][0]
assert rel_radar['type'] == 'related_to', f'无效关系类型应归related_to：{rel_radar["type"]}'
print(f'  ✓ 过滤后关系数={len(relations)}（原6个→2个），自环/悬空/重复/无效类型已清除')
print(f'    关系: {[(r["source"],r["target"],r["type"]) for r in relations]}')

print('\n=== 4. 规则降级方案：不提取通用词 ===')
content = """
2024年3月15日，销售张伟拜访了华为科技有限公司。
联系人：李明，电话13800138000。
华为科技有限公司正在使用数据管理平台，并计划采购新的雷达模拟器系统。
该系统由北京某研究所研发。
合同编号：HT-2024-001。
华为科技有限公司具备武器装备科研生产许可证。
项目名称：型号研制项目。
"""
result = _rule_based_extraction('拜访记录', content)
entities = result['entities']
entity_names = [e['name'] for e in entities]

print(f'  提取到的实体: {[(e["name"], e["type"]) for e in entities]}')

# 应提取
assert '张伟' in entity_names, f'应提取"张伟"：{entity_names}'
assert '李明' in entity_names, f'应提取"李明"：{entity_names}'
assert '华为科技有限公司' in entity_names, f'应提取"华为科技有限公司"：{entity_names}'
assert '数据管理平台' in entity_names, f'应提取"数据管理平台"（前缀清洗后）：{entity_names}'
assert '武器装备科研生产许可证' in entity_names, f'应提取资质：{entity_names}'

# 不应提取通用词
assert '系统' not in entity_names, '"系统"不应被提取'
assert '平台' not in entity_names, '"平台"不应被提取'
assert '项目' not in entity_names, '"项目"不应被提取'
assert '该公司' not in entity_names, '"该公司"不应被提取'

# 前缀清洗验证：不应出现"正在使用数据管理平台"这种长前缀
assert not any('正在使用' in n for n in entity_names), f'前缀清洗失败，仍有"正在使用"前缀：{entity_names}'
# "华为科技有限公司"不应被错误截断
assert '华为科技有限公司' in entity_names, '"华为科技有限公司"不应被前缀清洗截断'

print(f'  ✓ 提取到 {len(entities)} 个有效实体（无通用词/前缀已清洗/无错误截断）')

# 关系验证
relations = result['relations']
assert len(relations) > 0, '应构建关系'
uses_rels = [r for r in relations if r['type'] == 'uses']
assert any(r['source'] == '华为科技有限公司' and r['target'] == '数据管理平台' for r in uses_rels), \
    f'应构建"华为使用数据管理平台"关系：{[(r["source"],r["target"],r["type"]) for r in relations]}'
print(f'  ✓ 构建关系 {len(relations)} 条')

print('\n=== 5. 空数据/异常数据安全处理 ===')
assert _postprocess_extraction(None) == {'entities': [], 'relations': []}
assert _postprocess_extraction({}) == {'entities': [], 'relations': []}
assert _postprocess_extraction({'entities': [], 'relations': []}) == {'entities': [], 'relations': []}
assert _postprocess_extraction({'entities': 'not_a_list', 'relations': 123}) == {'entities': [], 'relations': []}
print('  ✓ 空数据/异常数据安全处理')

print('\n✅ 知识图谱实体构建优化 验证通过')
