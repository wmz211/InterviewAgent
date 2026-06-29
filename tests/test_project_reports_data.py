import unittest

from scripts.project_reports_data import PROJECT


class ProjectReportsDataTests(unittest.TestCase):
    def test_project_identity_and_team_are_stable(self):
        self.assertEqual(PROJECT["name"], "InterviewAgent 智能面试评估系统")
        self.assertEqual(PROJECT["planned_weeks"], 20)
        self.assertEqual(
            PROJECT["authors"],
            ["王明哲", "江悦铭", "周士斌"],
        )
        self.assertNotIn("王明哲", PROJECT["team"])
        self.assertEqual(len(PROJECT["team"]), 13)

    def test_planned_hours_total_matches_virtual_staffing_plan(self):
        total = sum(item["hours"] for item in PROJECT["phases"])
        role_total = sum(item["planned_hours"] for item in PROJECT["team"].values())
        self.assertEqual(total, 8440)
        self.assertEqual(role_total, total)

    def test_budget_components_reconcile_to_bac(self):
        labor = sum(item["labor_cost"] for item in PROJECT["phases"])
        direct = labor + sum(PROJECT["non_labor_costs"].values())
        reserve = round(direct * PROJECT["management_reserve_rate"])
        self.assertEqual(PROJECT["labor_cost"], labor)
        self.assertEqual(PROJECT["direct_cost"], direct)
        self.assertEqual(PROJECT["management_reserve"], reserve)
        self.assertEqual(PROJECT["bac"], direct + reserve)

    def test_planning_baseline_does_not_claim_execution_actuals(self):
        self.assertNotIn("actual_weeks", PROJECT)
        self.assertNotIn("actual_cost", PROJECT)
        self.assertNotIn("evm", PROJECT)


if __name__ == "__main__":
    unittest.main()
