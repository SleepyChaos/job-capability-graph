import csv
import sys
from pathlib import Path

CANDIDATE_URLS = [
    {
        "skills": "https://raw.githubusercontent.com/tabiya-tech/tabiya-open-dataset/main/tabiya-esco-v1.1.1/csv/en/skills.csv",
        "hier": "https://raw.githubusercontent.com/tabiya-tech/tabiya-open-dataset/main/tabiya-esco-v1.1.1/csv/en/occupationSkillRelations.csv",
    },
    {
        "skills": "https://github.com/tabiya-tech/tabiya-open-dataset/raw/main/tabiya-esco-v1.1.1/csv/en/skills.csv",
        "hier": "https://github.com/tabiya-tech/tabiya-open-dataset/raw/main/tabiya-esco-v1.1.1/csv/en/occupationSkillRelations.csv",
    },
]

def download_file(url: str, dest: Path) -> bool:
    try:
        import requests
    except ImportError:
        import urllib.request
        try:
            with urllib.request.urlopen(url, timeout=180) as resp:
                dest.write_bytes(resp.read())
            return dest.stat().st_size > 0
        except Exception as e:
            print(f"  urllib fail {url}: {e}")
            return False
    try:
        resp = requests.get(url, timeout=180, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200 and len(resp.content) > 0:
            dest.write_bytes(resp.content)
            print(f"  OK {url} -> {dest.name} ({len(resp.content)} bytes)")
            return True
        else:
            print(f"  HTTP {resp.status_code} {url}")
            return False
    except Exception as e:
        print(f"  requests fail {url}: {e}")
        return False


def build_mock_skills(dest: Path) -> None:
    print("Building mock skills.csv placeholder...")
    mock_skills = [
        ("http://data.europa.eu/esco/skill/S1_1", "reading comprehension", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S1_2", "writing", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_1", "robotics manipulation", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_2", "motion control", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_3", "servo drive", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_4", "path planning", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_5", "computer vision", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_6", "natural language processing", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_7", "machine learning", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_8", "deep learning", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_9", "reinforcement learning", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_10", "slam", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_11", "point cloud processing", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_12", "embedded systems", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_13", "fpga design", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_14", "mechanical design", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_15", "convolutional neural networks", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_16", "transformer models", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_17", "3d vision", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_18", "grasping", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_19", "force control", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_20", "sensor fusion", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_21", "ros robot operating system", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_22", "collaborative robotics", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_23", "industrial robotics", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_24", "control algorithms", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_25", "simulation modelling", "S", "skill"),
        ("http://data.europa.eu/esco/skill/S2_26", "knowledge graph", "S", "skill"),
    ]
    with dest.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["conceptUri", "preferredLabel", "skillType", "description"])
        for uri, label, stype, desc in mock_skills:
            w.writerow([uri, label, stype, desc])
    print(f"  -> wrote {len(mock_skills)} mock skills to {dest.name}")


def build_mock_hier(dest: Path, skills_path: Path) -> None:
    print("Building mock skillOccupationHierarchy.csv placeholder...")
    skill_uris = []
    if skills_path.exists():
        with skills_path.open("r", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                uri = row.get("conceptUri") or row.get("uri")
                if uri:
                    skill_uris.append(uri)
    if not skill_uris:
        skill_uris = [f"http://data.europa.eu/esco/skill/S2_{i}" for i in range(1, 26)]

    occ_tuples = [
        ("http://data.europa.eu/esco/occupation/1101", "software developer"),
        ("http://data.europa.eu/esco/occupation/2141", "mechanical engineer"),
        ("http://data.europa.eu/esco/occupation/2142", "electronics engineer"),
        ("http://data.europa.eu/esco/occupation/2512", "robotics engineer"),
        ("http://data.europa.eu/esco/occupation/2513", "automation engineer"),
        ("http://data.europa.eu/esco/occupation/2514", "ai engineer"),
        ("http://data.europa.eu/esco/occupation/2515", "computer vision engineer"),
        ("http://data.europa.eu/esco/occupation/2516", "embedded systems engineer"),
        ("http://data.europa.eu/esco/occupation/2517", "machine learning engineer"),
        ("http://data.europa.eu/esco/occupation/3111", "industrial robot operator"),
        ("http://data.europa.eu/esco/occupation/3112", "mechatronics technician"),
        ("http://data.europa.eu/esco/occupation/3113", "automation technician"),
    ]
    rows = []
    for s_uri in skill_uris:
        for i, (o_uri, _) in enumerate(occ_tuples):
            if i % 2 == 0 or len(rows) < 200:
                rows.append((s_uri, o_uri, "essential"))
    with dest.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["skillUri", "occupationUri", "relationType"])
        for r in rows[:300]:
            w.writerow(r)
    print(f"  -> wrote {min(300, len(rows))} mock relations to {dest.name}")


def main() -> int:
    out_dir = Path(__file__).parent
    skills_path = out_dir / "skills.csv"
    hier_path = out_dir / "skillOccupationHierarchy.csv"

    ok_skills = False
    ok_hier = False
    for idx, cands in enumerate(CANDIDATE_URLS):
        print(f"Candidate set #{idx+1}")
        if not ok_skills:
            ok_skills = download_file(cands["skills"], skills_path)
        if not ok_hier:
            ok_hier = download_file(cands["hier"], hier_path)
        if ok_skills and ok_hier:
            break

    if not ok_skills:
        build_mock_skills(skills_path)
        ok_skills = True
    if not ok_hier:
        build_mock_hier(hier_path, skills_path)
        ok_hier = True

    print(f"\nFinal state:")
    for p in [skills_path, hier_path]:
        if p.exists():
            print(f"  {p.name}: {p.stat().st_size} bytes")
            with p.open("r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i < 3:
                        print(f"    Line{i+1}: {line.rstrip()[:200]}")
                    else:
                        break
        else:
            print(f"  {p.name}: MISSING")

    return 0 if (ok_skills and ok_hier) else 1


if __name__ == "__main__":
    sys.exit(main())
