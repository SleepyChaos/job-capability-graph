"""Download public map geometry/centres only; no enterprise data leaves the machine."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json
from urllib.request import urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / 'data/reference/industry-geo'
BASE = 'https://geo.datav.aliyun.com/areas_v3/bound/'

def download(code: int) -> dict:
    path = TARGET / f'{code}_full.json'
    if not path.exists():
        try:
            with urlopen(f'{BASE}{code}_full.json', timeout=30) as response:
                path.write_bytes(response.read())
        except HTTPError as exc:
            if exc.code == 404:
                print(f'No prefecture geometry for {code}; retain province-level data only.')
                return {'features': []}
            raise
    return json.loads(path.read_text(encoding='utf-8'))

def main():
    country = json.loads((TARGET / 'china-provinces.geo.json').read_text(encoding='utf-8'))
    # Prefecture centres for provinces represented in the supplied enterprise workbook.
    codes = [130000,140000,150000,210000,220000,230000,320000,330000,340000,
             350000,360000,370000,410000,420000,430000,440000,450000,510000,
             610000,620000,650000,710000]
    centres = {}
    for feature in country['features']:
        p = feature['properties']
        if p.get('center') and p.get('name'):
            centres[p['name']] = p['center']
    with ThreadPoolExecutor(max_workers=4) as pool:
        for doc in pool.map(download, codes):
            for feature in doc['features']:
                p = feature['properties']
                if p.get('center') and p.get('name'):
                    centres[p['name']] = p['center']
    result = {'source': 'DataV.GeoAtlas', 'url': BASE, 'precision': 'city-centre, not office address', 'centres': centres}
    (TARGET / 'city-centres.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'cityCentreCount': len(centres)}))

if __name__ == '__main__':
    main()
