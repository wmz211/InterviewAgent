import tempfile
import unittest
import zipfile
from pathlib import Path

from docx import Document

from scripts.generate_project_management_reports import (
    add_cover,
    add_management_table,
    new_document,
)


class ProjectReportBuilderTests(unittest.TestCase):
    def test_document_uses_required_geometry_and_styles(self):
        doc = new_document("测试报告")
        add_cover(doc, "测试报告", "结构冒烟测试")
        add_management_table(doc, ["字段", "内容"], [["项目", "InterviewAgent"]], [2200, 7160])

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "smoke.docx"
            doc.save(path)
            loaded = Document(path)
            section = loaded.sections[0]
            self.assertEqual(round(section.page_width.inches, 1), 8.5)
            self.assertEqual(round(section.page_height.inches, 1), 11.0)
            self.assertEqual(round(section.left_margin.inches, 1), 1.0)
            self.assertEqual(loaded.styles["Normal"].font.name, "Calibri")

            with zipfile.ZipFile(path) as package:
                document_xml = package.read("word/document.xml").decode("utf-8")
                footer_xml = package.read("word/footer1.xml").decode("utf-8")
                self.assertIn('<w:tblW w:type="dxa" w:w="9360"/>', document_xml)
                self.assertIn('w:gridCol w:w="2200"', document_xml)
                self.assertIn('w:gridCol w:w="7160"', document_xml)
                self.assertIn('w:fldCharType="begin"', footer_xml)
                self.assertIn("PAGE", footer_xml)


if __name__ == "__main__":
    unittest.main()
