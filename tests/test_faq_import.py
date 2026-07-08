from html import escape
from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.main import app
from app.services.faq_import import FaqImportService

client = TestClient(app)


def build_test_xlsx(sheets: dict[str, list[list[str | None]]]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        workbook_sheets = []
        workbook_rels = []
        for index, (sheet_name, rows) in enumerate(sheets.items(), start=1):
            workbook_sheets.append(
                f'<sheet name="{escape(sheet_name)}" sheetId="{index}" r:id="rId{index}"/>'
            )
            workbook_rels.append(
                f'<Relationship Id="rId{index}" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                f'relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
            )
            archive.writestr(f"xl/worksheets/sheet{index}.xml", build_sheet_xml(rows))

        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f"<sheets>{''.join(workbook_sheets)}</sheets>"
            "</workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{''.join(workbook_rels)}"
            "</Relationships>",
        )
    return buffer.getvalue()


def build_sheet_xml(rows: list[list[str | None]]) -> str:
    row_xml = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row):
            if value is None:
                continue
            cell_ref = f"{column_name(column_index)}{row_index}"
            cells.append(
                f'<c r="{cell_ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
            )
        row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(row_xml)}</sheetData>'
        "</worksheet>"
    )


def column_name(index: int) -> str:
    result = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def test_parse_faq_import_service() -> None:
    content = build_test_xlsx(
        {
            "账户管理": [
                ["分类", "提问示例", "解答", "对应操作指引图"],
                ["注册", "怎么注册；如何注册", "进入注册页提交手机号。", "https://example.com/a.png"],
                ["注册", "", "缺少问题"],
            ],
            "交易": [
                ["一级分类", "二级分类", "分类", "提问示例", "解答"],
                ["售前", "订单", "关闭", "订单为什么关闭", "超时未支付会关闭。"],
            ],
        }
    )

    data = FaqImportService().parse_excel(
        content=content,
        file_name="faq.xlsx",
        preview_limit=10,
    )

    assert data.total_rows == 3
    assert data.valid_rows == 2
    assert data.invalid_rows == 1
    assert data.items[0].standard_question == "怎么注册"
    assert data.items[0].paraphrases == ["如何注册"]
    assert data.items[1].category_l1 == "售前"
    assert data.items[1].category_l2 == "订单"
    assert data.items[1].category_l3 == "关闭"
    assert data.issues[0].field == "提问示例"


def test_parse_faq_import_blocks_duplicate_questions() -> None:
    content = build_test_xlsx(
        {
            "账户": [
                ["分类", "提问示例", "解答"],
                ["注册", "怎么注册", "进入注册页提交手机号。"],
                ["登录", "怎么注册", "打开登录页后选择注册。"],
            ]
        }
    )

    data = FaqImportService().parse_excel(
        content=content,
        file_name="faq.xlsx",
        preview_limit=10,
    )

    assert data.valid_rows == 2
    assert all(item.blocked for item in data.items)
    assert any(
        issue.level == "error" and "同一 Excel 内标准问题重复" in issue.message
        for issue in data.issues
    )


def test_parse_faq_import_endpoint(monkeypatch) -> None:
    async def noop_mark_existing_conflicts(
        self: FaqImportService,
        items: object,
        issues: object,
    ) -> None:
        return None

    monkeypatch.setattr(
        FaqImportService,
        "_mark_existing_question_conflicts",
        noop_mark_existing_conflicts,
    )
    content = build_test_xlsx(
        {
            "FAQ": [
                ["分类", "提问示例", "解答"],
                ["账户", "怎么改手机号", "进入账号与安全页面修改。"],
            ]
        }
    )

    response = client.post(
        "/api/v1/faqs/import/parse",
        files={
            "file": (
                "faq.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "OK"
    assert body["data"]["valid_rows"] == 1
    assert body["data"]["items"][0]["standard_question"] == "怎么改手机号"
