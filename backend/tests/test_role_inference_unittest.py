from __future__ import annotations

import unittest

from app.modules.graph.role_inference import aggregate_confirmed_profiles, infer_roles


class RoleInferenceTest(unittest.TestCase):
    def test_legacy_mapping_is_reference_and_not_mutated(self):
        graph = self._graph()
        original = graph["jobs"][0]["standardRoleId"]
        result = infer_roles(graph, {"jdTechnologyInheritance": []})
        self.assertEqual(original, graph["jobs"][0]["standardRoleId"])
        self.assertEqual("historical_excel_reference", result["jobRoleInferences"][0]["legacyMapping"]["source"])

    def test_job_does_not_prove_itself_through_legacy_role_prototype(self):
        result = infer_roles(self._graph(), {"jdTechnologyInheritance": []})
        best = result["jobRoleInferences"][0]["standardRole"]["result"]
        self.assertEqual(0.0, best["componentScores"]["duty"])
        self.assertEqual(0.0, best["componentScores"]["skill"])

    def test_profile_evidence_is_point_specific(self):
        items = [
            self._confirmed("j1", "动力学建模"),
            self._confirmed("j2", "动力学建模"),
            self._confirmed("j3", "C++"),
        ]
        profiles = aggregate_confirmed_profiles(items)
        skills = profiles[0]["dimensions"]["skills"]
        dynamics = next(x for x in skills if x["name"] == "动力学建模")
        self.assertEqual(2, dynamics["supportCount"])
        self.assertEqual(["j1", "j2"], dynamics["evidenceJdIds"])
        self.assertAlmostEqual(2 / 3, dynamics["coverage"], places=5)

    @staticmethod
    def _confirmed(job_id, skill):
        return {
            "jdId": job_id, "occId": job_id,
            "standardRole": {"status": "confirmed", "result": {"roleId": "r1", "roleName": "运动控制算法工程师"}},
            "profileExtraction": {"responsibilities": [], "skills": [{"name": skill, "normalizedKey": skill, "method": "test", "evidenceSnippets": []}], "abilities": [], "scenarios": [], "conditions": []},
        }

    @staticmethod
    def _graph():
        return {
            "clusters": [{"id": "c1", "name": "运动控制"}],
            "standardRoles": [{"id": "r1", "name": "运动控制算法工程师", "clusterId": "c1", "categoryName": "算法"}],
            "jobs": [{"id": "j1", "occId": "o1", "title": "运动控制算法工程师", "clusterId": "c1", "clusterName": "运动控制", "categoryName": "算法", "standardRoleId": "r1", "standardRoleName": "运动控制算法工程师", "profile": {"responsibilities": ["负责运动控制"], "skills": ["MPC"], "abilities": [], "scenarios": [], "conditions": [], "jdEvidence": ["负责运动控制与MPC开发"]}}],
        }


if __name__ == "__main__":
    unittest.main()
