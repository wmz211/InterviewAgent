# InterviewAgent Project Management Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate and visually verify nine internally consistent Chinese DOCX project-management reports for the InterviewAgent software project.

**Architecture:** A single structured Python builder owns the shared project baseline and document style system, while report-specific functions compose narrative sections and management tables from that baseline. Structural audits validate package integrity and cross-report facts; the bundled DOCX renderer produces page images for final visual inspection.

**Tech Stack:** Bundled Python 3, python-docx, OOXML, LibreOffice headless renderer, Poppler, Pillow.

---

### Task 1: Establish Shared Project Baseline

**Files:**
- Create: `scripts/project_reports_data.py`
- Create: `tests/test_project_reports_data.py`

- [ ] Define immutable project identity, three-person role map, 20-week baseline, 21-week actual duration, WBS, resource rates, phase work hours, non-labor costs, quality targets, risks and final actuals.
- [ ] Add tests asserting planned hours total 2,400, phase costs sum to BAC, actual cost produces the reported variance, role assignments are unique, and planned/actual durations remain 20/21 weeks.
- [ ] Run `python -m unittest tests.test_project_reports_data -v` and confirm all arithmetic and identity checks pass.

### Task 2: Build the DOCX Style and Layout Layer

**Files:**
- Create: `scripts/generate_project_management_reports.py`
- Create: `tests/test_project_report_builder.py`

- [ ] Implement the `standard_business_brief` token map with Letter page geometry, 1-inch margins, Calibri 11 pt body, explicit heading spacing, fixed DXA table geometry, Chinese-compatible East Asian font settings, running headers, footers and page fields.
- [ ] Implement reusable cover, document-control block, heading, prose, real list numbering, table, caption, page-break and static contents helpers.
- [ ] Add tests that generate a smoke document and inspect OOXML for page dimensions, styles, numbering, table grids, margins, headers and footer page fields.
- [ ] Run `python -m unittest tests.test_project_report_builder -v` and confirm the package checks pass.

### Task 3: Author the Nine Reports

**Files:**
- Modify: `scripts/generate_project_management_reports.py`
- Create: `output/project_management_reports/*.docx`

- [ ] Implement report functions for the proposal, feasibility analysis, project plan, estimates, progress/cost control, quality, risk, team management and project summary.
- [ ] Include WBS/WBS dictionary, resource plan, 20-week schedule, cost baseline, risk plan and quality plan in the project plan.
- [ ] Include resource, duration and cost estimation methods and calculations in the estimate report.
- [ ] Include PV/EV/AC and EVM calculations at a defined status date in the control report, plus final forecast.
- [ ] Include AI-specific quality measures and risk responses, a three-person RACI/skills matrix, and a final 21-week closeout with residual risks.
- [ ] Run the generator and confirm exactly nine DOCX files are produced with Chinese report titles and non-trivial file sizes.

### Task 4: Audit Content and Cross-Report Consistency

**Files:**
- Create: `scripts/audit_project_management_reports.py`
- Create: `tests/test_project_report_content.py`

- [ ] Extract DOCX text and assert every file contains the project name, correct team members, report-specific mandatory sections and no placeholder markers.
- [ ] Verify all baseline references use 20 weeks, all final references use 21 weeks where applicable, and all shared cost figures match the structured baseline.
- [ ] Inspect all tables for fixed geometry, repeat-header markup and absence of fixed row heights.
- [ ] Run `python -m unittest tests.test_project_report_content -v` and the standalone audit, requiring zero errors.

### Task 5: Render and Visually Verify Every Page

**Files:**
- Create: `output/project_management_reports/_qa/<report>/page-*.png`
- Modify if needed: `scripts/generate_project_management_reports.py`

- [ ] Render each DOCX with the bundled `render_docx.py` into a dedicated QA directory.
- [ ] Build contact sheets for each report and inspect every rendered page for missing Chinese glyphs, clipping, overlap, broken tables, heading orphans and abnormal blank pages.
- [ ] Correct layout defects, regenerate affected reports and re-render until the latest output is clean.
- [ ] Run a final command that reports nine DOCX files, nine successful render directories, all structural tests passing and no audit errors.

### Task 6: Deliver

**Files:**
- Final: `output/project_management_reports/*.docx`

- [ ] Remove or exclude QA intermediates from the user-facing deliverable list.
- [ ] Provide direct links to all nine final DOCX files and summarize the shared 20-week plan/21-week actual management scenario.
