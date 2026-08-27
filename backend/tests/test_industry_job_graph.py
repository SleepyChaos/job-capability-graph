"""Regression checks for the enterprise-led industry graph snapshot."""
import json
from pathlib import Path
import unittest
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]

class IndustryJobGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / 'frontend/public/enterprise-industry-graph.json').read_text(encoding='utf-8'))
        cls.graph = json.loads((ROOT / 'frontend/public/job-ecosystem-graph.json').read_text(encoding='utf-8'))

    def test_full_source_catalogue_not_only_mapped_enterprises(self):
        enterprises = self.data['enterprises']
        self.assertEqual(len(enterprises), 632)
        self.assertEqual(len({e['id'] for e in enterprises}), len(enterprises))
        self.assertTrue(all(e['name'] for e in enterprises))
        self.assertEqual(sum(not e['jobCount'] for e in enterprises), 530)
        self.assertEqual(self.data['metadata']['blankRowsExcluded'], [634])

    def test_explicit_job_mapping_reconciles_without_duplicates(self):
        ids = [job_id for e in self.data['enterprises'] for job_id in e['jobIds']]
        self.assertEqual(len(ids), 4472)
        self.assertEqual(len(set(ids)), len(ids))
        self.assertTrue(set(ids).issubset({j['id'] for j in self.graph['jobs']}))
        self.assertEqual(len(ids) + self.data['metadata']['pendingJobCount'], 4655)
        self.assertTrue(all(len(e['jobIds']) == e['jobCount'] for e in self.data['enterprises']))

    def test_all_three_overview_views_use_same_jd_population(self):
        overview = self.data['overview']
        self.assertEqual(sum(x['count'] for x in overview['stageDemand']), 4472)
        self.assertEqual(sum(x['count'] for x in overview['financingDemand']), 4472)
        self.assertEqual(sum(sum(x['values']) for x in overview['directionStage']), 4472)
        self.assertEqual(len(overview['directionStage']), 6)

    def test_industry_categories_follow_user_mapping(self):
        taxonomy = {c['name']: c['primaryStage'] for c in self.data['categories']}
        self.assertEqual(len(taxonomy), 11)
        for e in self.data['enterprises']:
            expected = taxonomy[e['industryCategory']]
            if e['industryCategory'] == 'AI大模型' and e['originalStage'] == '横向支撑':
                expected = '横向支撑'
            self.assertEqual(e['industryStage'], expected)

    def test_recruitment_evidence_kept_for_unmapped_entities(self):
        enterprises = self.data['enterprises']
        self.assertEqual(sum(bool(e['recruitmentLinks']) for e in enterprises), 522)
        self.assertTrue(any(not e['jobCount'] and e['reportedOpenings'] > 0 and e['recruitmentLinks'] for e in enterprises))
        for e in enterprises:
            urls = [link['url'] for link in e['recruitmentLinks']]
            self.assertEqual(len(urls), len(set(urls)))
            self.assertTrue(all(urlparse(url).scheme in ('http', 'https') and urlparse(url).netloc for url in urls))

    def test_headquarters_are_city_centres_not_fabricated_office_locations(self):
        enterprises = self.data['enterprises']
        self.assertEqual(sum(e['headquartersPoint'] is not None for e in enterprises), self.data['metadata']['enterprisesWithHeadquartersPoints'])
        self.assertTrue(all(e['headquartersPoint'] is None for e in enterprises if e['companyRegion'] == '海外'))
        self.assertTrue(all(e['headquartersCoordinateLevel'] == '城市中心示意' for e in enterprises if e['headquartersPoint']))
        self.assertGreater(len(self.data['map']['features']), 30)

if __name__ == '__main__':
    unittest.main()
