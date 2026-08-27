"""Full enterprise catalogue + explicit v4 enhancement mappings; source XLSX files are read-only."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import openpyxl

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'data/source/20260827/industry'
LIBRARY = SOURCE / '具身智能企业数据_整合去重_完整.xlsx'
ENHANCED = SOURCE / '岗位信息v4_企业增强分析与图谱.xlsx'
BASELINE = SOURCE / '岗位信息v4.xlsx'
GEO = ROOT / 'data/reference/industry-geo'
STAGES = ['上游', '中游', '下游', '横向支撑']
CATEGORY_STAGES = {
    '关键材料': '上游', '感知系统': '上游', '执行系统': '上游',
    '检测/测试/测量': '上游', '加工设备及智能装备': '上游',
    '具身智能本体': '中游', '软件与算法': '中游', 'AI大模型': '中游',
    '决策认知系统': '中游', '场景应用与解决方案': '下游', '政策与生态': '横向支撑',
}
REGIONS = {
    '华北': ['北京', '天津', '河北', '山西', '内蒙古'],
    '东北': ['辽宁', '吉林', '黑龙江'],
    '华东': ['上海', '江苏', '浙江', '安徽', '福建', '江西', '山东', '台湾'],
    '华中': ['河南', '湖北', '湖南'],
    '华南': ['广东', '广西', '海南', '香港', '澳门'],
    '西南': ['重庆', '四川', '贵州', '云南', '西藏'],
    '西北': ['陕西', '甘肃', '青海', '宁夏', '新疆'],
}

def clean(value):
    return '' if value is None else str(value).strip()

def key(value):
    return re.sub(r'[^a-z0-9\u4e00-\u9fff]', '', clean(value).lower())

def read_rows(path, sheet_name):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    iterator = wb[sheet_name].iter_rows(values_only=True)
    header = [clean(v) for v in next(iterator)]
    rows = [dict(zip(header, row)) for row in iterator]
    wb.close()
    return rows

def region_for(province, country):
    for region, provinces in REGIONS.items():
        if any(province.startswith(p) for p in provinces):
            return region
    return '海外' if country and country not in ['中国', '待核实'] else '待核实'

def get_links(value, label):
    result = []
    for url in re.findall(r'https?://[^\s<>"\u3000;；，、\u4e00-\u9fff]+', clean(value)):
        url = url.rstrip(').。】]，,；;')
        if url:
            result.append({'label': label, 'url': url})
    return result

def counts(values):
    return [{'name': name, 'count': count} for name, count in Counter(values).most_common()]

def project(lon, lat):
    return [round(34 + (lon - 73) * 13.5, 2), round(20 + (54 - lat) * 12.5, 2)]

def geometry_path(geometry):
    polygons = geometry['coordinates'] if geometry['type'] == 'MultiPolygon' else [geometry['coordinates']]
    parts = []
    for polygon in polygons:
        for ring in polygon:
            points = [project(*p[:2]) for p in ring]
            if points:
                parts.append('M' + 'L'.join(f'{x},{y}' for x, y in points) + 'Z')
    return ''.join(parts)

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    raw_library = read_rows(LIBRARY, 'Sheet1')
    enhanced = read_rows(ENHANCED, '岗位信息v4_企业增强')
    baseline = read_rows(BASELINE, '岗位信息v4')
    graph = json.loads((ROOT / 'data/processed/job_graph/job-ecosystem-graph.json').read_text(encoding='utf-8'))
    jobs_by_occ = {j['occId']: j for j in graph['jobs']}
    baseline_ids = {clean(r['occ_id']) for r in baseline if clean(r.get('occ_id'))}
    enhanced = [r for r in enhanced if clean(r.get('occ_id'))]
    assert baseline_ids == {clean(r['occ_id']) for r in enhanced}, 'v4/enhancement identifiers diverged'
    assert baseline_ids == set(jobs_by_occ), 'runtime JD identifiers differ from source v4'

    geo = json.loads((GEO / 'china-provinces.geo.json').read_text(encoding='utf-8'))
    centres = json.loads((GEO / 'city-centres.json').read_text(encoding='utf-8'))['centres']
    city_centres = {re.sub(r'市$', '', name): point for name, point in centres.items()}
    enterprises = []
    blanks = []
    for row_index, row in enumerate(raw_library, start=2):
        name = clean(row.get('企业名称'))
        if not name:
            blanks.append(row_index)
            continue
        category = clean(row.get('产业链(12类标准)')) or '待分类'
        original_stage = clean(row.get('层级'))
        stage = CATEGORY_STAGES.get(category, original_stage or '待分类')
        if category == 'AI大模型' and original_stage == '横向支撑':
            stage = '横向支撑'
        province, city, country = (clean(row.get(f)) for f in ['省份', '城市', '国家'])
        links = []
        fields = [('官网岗位招聘链接', '招聘官网'),
                  ('猎聘招聘链接（https://www.liepin.com/company-jobs/xxx/）', '猎聘招聘'),
                  ('其他第三方招聘链接（boss；智联；脉脉…）', '其他招聘平台')]
        for field, label in fields:
            links += get_links(row.get(field), label)
        unique_links = list({link['url']: link for link in links}.values())
        raw_openings = clean(row.get('在聘岗位数量'))
        point = city_centres.get(city.removesuffix('市'))
        # Coordinates are city centres, never guessed street/office addresses.
        if country not in ['中国', ''] or province not in {p for ps in REGIONS.values() for p in ps}:
            point = None
        enterprise = {
            'id': 'catalog-' + hashlib.sha1(name.encode()).hexdigest()[:12],
            'name': name, 'aliases': clean(row.get('英文名/别名')),
            'industryStage': stage, 'industryCategory': category, 'originalStage': original_stage,
            'companySpecialty': clean(row.get('细分领域')), 'financingRound': clean(row.get('融资轮次分类')) or '未披露',
            'financingDetail': clean(row.get('融资阶段')), 'province': province, 'city': city, 'country': country,
            'district': clean(row.get('区/县')), 'companyRegion': region_for(province, country),
            'headquartersCity': clean(row.get('总部城市')), 'headquartersPoint': project(*point) if point else None,
            'headquartersCoordinateLevel': '城市中心示意' if point else '未定位',
            'website': next(iter(get_links(row.get('官网链接'), '企业官网')), {}).get('url', ''),
            'recruitmentLinks': unique_links, 'reportedOpeningsRaw': raw_openings,
            'reportedOpenings': int(float(raw_openings)) if re.fullmatch(r'\d+(?:\.0+)?', raw_openings) else None,
            'recruitmentNotes': clean(row.get('备注')), 'recruitmentSource': clean(row.get('岗位数据来源')),
            'products': clean(row.get('代表产品')), 'productType': clean(row.get('产品类型')),
            'features': clean(row.get('关键特性/参数')), 'production': clean(row.get('量产进展')),
            'operatingPath': clean(row.get('运营路径')), 'sourceNotes': clean(row.get('数据来源')),
            'sourceRow': row_index, 'jobIds': [], 'jobCount': 0,
        }
        enterprises.append(enterprise)
    by_name = {e['name']: e for e in enterprises}
    normalized_names = defaultdict(list)
    for e in enterprises:
        normalized_names[key(e['name'])].append(e)
    assert len(by_name) == len(enterprises), 'duplicate exact enterprise names'
    matched_rows = []
    unmatched = []
    mappings = []
    for row in enhanced:
        occ = clean(row['occ_id'])
        canonical_name = clean(row.get('企业库标准名称'))
        e = by_name.get(canonical_name)
        candidates = normalized_names.get(key(canonical_name), [])
        if e is None and len(candidates) == 1:
            e = candidates[0]
        if clean(row.get('企业属性补全状态')) != '已匹配' or not e:
            unmatched.append(occ)
            continue
        e['jobIds'].append(jobs_by_occ[occ]['id'])
        e['jobCount'] += 1
        matched_rows.append(row)
        mappings.append({'occId': occ, 'enterpriseId': e['id'], 'method': clean(row.get('企业匹配方式')), 'confidence': clean(row.get('企业匹配置信度'))})

    directions = [d['name'] for d in graph['directions']]
    stage_counts = Counter(clean(r.get('产业链层级')) or '待补全' for r in matched_rows)
    finance_counts = counts(clean(r.get('融资轮次')) or '未披露' for r in matched_rows)
    matrix = [
        {'direction': direction, 'values': [sum(clean(r.get('职业方向')) == direction and clean(r.get('产业链层级')) == stage for r in matched_rows) for stage in STAGES]}
        for direction in directions
    ]
    features = []
    for feature in geo['features']:
        p = feature['properties']
        name = p.get('name', '')
        features.append({'name': name, 'region': region_for(name, '中国'), 'path': geometry_path(feature['geometry'])})
    metadata = {
        'generatedAt': datetime.now(timezone.utc).isoformat(), 'libraryFile': LIBRARY.name,
        'enhancementFile': ENHANCED.name, 'baselineFile': BASELINE.name,
        'libraryDataRows': len(raw_library), 'enterpriseCount': len(enterprises), 'blankRowsExcluded': blanks,
        'normalizationConflicts': [[e['name'] for e in group] for group in normalized_names.values() if len(group) > 1],
        'jobCount': len(enhanced), 'mappedJobCount': len(matched_rows), 'pendingJobCount': len(unmatched),
        'enterprisesWithJobs': sum(e['jobCount'] > 0 for e in enterprises),
        'enterprisesWithoutJobs': sum(e['jobCount'] == 0 for e in enterprises),
        'enterprisesWithRecruitmentLinks': sum(bool(e['recruitmentLinks']) for e in enterprises),
        'enterprisesWithReportedOpenings': sum(e['reportedOpenings'] is not None for e in enterprises),
        'enterprisesWithHeadquartersPoints': sum(e['headquartersPoint'] is not None for e in enterprises),
        'hashes': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [LIBRARY, ENHANCED, BASELINE]},
        'countNote': '在聘岗位数量是企业库收录快照，非招聘人数，非实时值；与已映射JD数不可相加。',
        'overviewNote': '需求图仅统计企业增强表中已匹配的v4岗位样本，每条JD计一次；不是全市场招聘总量。',
        'geographySource': 'DataV.GeoAtlas · 城市中心示意，非企业精确地址',
        'geographySourceUrl': 'https://datav.aliyun.com/portal/school/atlas/area_selector',
    }
    payload = {
        'metadata': metadata, 'enterprises': enterprises,
        'stages': STAGES,
        'categories': [{'name': name, 'primaryStage': stage, 'note': '中游为主，部分横向支撑' if name == 'AI大模型' else ''} for name, stage in CATEGORY_STAGES.items()],
        'overview': {'stageDemand': [{'name': s, 'count': stage_counts[s]} for s in STAGES], 'financingDemand': finance_counts, 'directionStage': matrix},
        'map': {'width': 920, 'height': 690, 'features': features},
    }
    assert sum(e['jobCount'] for e in enterprises) == len(matched_rows)
    assert sum(x['count'] for x in payload['overview']['stageDemand']) == len(matched_rows)
    assert sum(sum(x['values']) for x in matrix) == len(matched_rows)
    assert len(matched_rows) + len(unmatched) == len(enhanced)
    out = ROOT / 'data/processed/industry_graph'
    out.mkdir(parents=True, exist_ok=True)
    for target in [out / 'enterprise-industry-graph.json', ROOT / 'frontend/public/enterprise-industry-graph.json']:
        target.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    (out / 'audit.json').write_text(json.dumps({'metadata': metadata, 'mappings': mappings, 'pendingOccIds': unmatched}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(metadata, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
