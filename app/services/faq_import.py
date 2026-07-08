from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError
from app.models.faq import KbFaq
from app.repositories.faq import FaqRepository
from app.schemas.faq_import import (
    FaqImportConfirmData,
    FaqImportConfirmItem,
    FaqImportIssue,
    FaqImportParseData,
    FaqImportPreviewItem,
    FaqImportSheetSummary,
)

XML_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkg_rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

HEADER_ALIASES = {
    "category_l1": {"一级分类", "大类", "主分类"},
    "category_l2": {"二级分类", "子分类"},
    "category_l3": {"三级分类", "细分类"},
    "question": {"提问示例", "问题", "标准问题", "用户问题", "问法"},
    "answer": {"解答", "答案", "标准答案", "回复"},
    "image_url": {"对应操作指引图", "操作指引图", "图片", "图片链接", "指引图"},
}


@dataclass
class XlsxSheet:
    name: str
    rows: list[list[str | None]]


class FaqImportService:
    def __init__(self, session: AsyncSession | None = None):
        self.session = session
        self.repository = FaqRepository(session) if session is not None else None

    def parse_excel(
        self,
        *,
        content: bytes,
        file_name: str,
        preview_limit: int,
    ) -> FaqImportParseData:
        sheets = read_xlsx(content)
        items: list[FaqImportPreviewItem] = []
        issues: list[FaqImportIssue] = []
        sheet_summaries: list[FaqImportSheetSummary] = []
        seen_questions: dict[str, tuple[str, int]] = {}

        for sheet in sheets:
            summary = self._parse_sheet(
                sheet=sheet,
                items=items,
                issues=issues,
                seen_questions=seen_questions,
                preview_limit=preview_limit,
            )
            sheet_summaries.append(summary)

        self._mark_file_question_conflicts(items, issues)
        valid_rows = sum(sheet.valid_rows for sheet in sheet_summaries)
        invalid_rows = sum(sheet.invalid_rows for sheet in sheet_summaries)
        warning_rows = sum(1 for item in items if item.warnings or item.blocking_reasons)
        return FaqImportParseData(
            file_name=file_name,
            total_rows=sum(sheet.total_rows for sheet in sheet_summaries),
            valid_rows=valid_rows,
            invalid_rows=invalid_rows,
            warning_rows=warning_rows,
            preview_limit=preview_limit,
            sheets=sheet_summaries,
            items=items[:preview_limit],
            issues=issues,
        )

    async def parse_excel_with_conflicts(
        self,
        *,
        content: bytes,
        file_name: str,
        preview_limit: int,
    ) -> FaqImportParseData:
        parsed = self.parse_excel(
            content=content,
            file_name=file_name,
            preview_limit=preview_limit,
        )
        await self._mark_existing_question_conflicts(parsed.items, parsed.issues)
        parsed.warning_rows = sum(
            1 for item in parsed.items if item.warnings or item.blocking_reasons
        )
        return parsed

    async def confirm_excel(
        self,
        *,
        content: bytes,
        file_name: str,
        status: int,
        updated_by: str,
    ) -> FaqImportConfirmData:
        if self.session is None or self.repository is None:
            raise RuntimeError("confirm_excel requires a database session")

        parsed = await self.parse_excel_with_conflicts(
            content=content,
            file_name=file_name,
            preview_limit=5000,
        )
        now = datetime.now()
        result_items: list[FaqImportConfirmItem] = []
        created = 0
        updated = 0
        failed = 0
        skipped = parsed.invalid_rows

        try:
            for item in parsed.items:
                if item.blocked:
                    skipped += 1
                    result_items.append(
                        FaqImportConfirmItem(
                            sheet=item.sheet,
                            row=item.row,
                            knowledge_id=item.knowledge_id,
                            action="skipped",
                            success=False,
                            message="；".join(item.blocking_reasons) or "存在冲突，已跳过入库",
                        )
                    )
                    continue
                try:
                    async with self.session.begin_nested():
                        existing = await self.repository.get_by_knowledge_id(
                            item.knowledge_id,
                            for_update=True,
                        )
                        if existing is None:
                            faq = self._build_new_faq(
                                item=item,
                                status=status,
                                updated_by=updated_by,
                                now=now,
                            )
                            self.session.add(faq)
                            await self.session.flush()
                            action = "created"
                        else:
                            faq = existing
                            self._apply_import_item(
                                faq=faq,
                                item=item,
                                status=status,
                                updated_by=updated_by,
                                now=now,
                            )
                            action = "updated"

                        await self.repository.replace_paraphrases(
                            faq_id=faq.id,
                            values=item.paraphrases,
                            updated_by=updated_by,
                            now=now,
                        )
                    if action == "created":
                        created += 1
                    else:
                        updated += 1
                    result_items.append(
                        FaqImportConfirmItem(
                            sheet=item.sheet,
                            row=item.row,
                            knowledge_id=item.knowledge_id,
                            faq_id=faq.id,
                            action=action,
                            success=True,
                            message="新增成功" if action == "created" else "更新成功",
                        )
                    )
                except Exception as exc:
                    failed += 1
                    result_items.append(
                        FaqImportConfirmItem(
                            sheet=item.sheet,
                            row=item.row,
                            knowledge_id=item.knowledge_id,
                            action="failed",
                            success=False,
                            message=str(exc)[:500],
                        )
                    )

            await self.session.commit()
        except BusinessError:
            raise
        except Exception as exc:
            await self.session.rollback()
            raise BusinessError(
                "FAQ 导入入库失败，已回滚本次全部写入",
                code="FAQ_IMPORT_CONFIRM_FAILED",
                status_code=500,
                details={
                    "error": str(exc),
                    "items": [item.model_dump() for item in result_items],
                },
            ) from exc

        return FaqImportConfirmData(
            file_name=file_name,
            total_rows=parsed.total_rows,
            valid_rows=parsed.valid_rows,
            invalid_rows=parsed.invalid_rows,
            created=created,
            updated=updated,
            failed=failed,
            skipped=skipped,
            status=status,
            items=result_items,
            issues=parsed.issues,
        )

    async def _mark_existing_question_conflicts(
        self,
        items: list[FaqImportPreviewItem],
        issues: list[FaqImportIssue],
    ) -> None:
        if self.repository is None:
            return
        for item in items:
            existing = await self.repository.get_by_standard_question(item.standard_question)
            if existing is None or existing.knowledge_id == item.knowledge_id:
                continue
            reason = (
                f"标准问题已存在于知识库：{existing.knowledge_id}，"
                "默认跳过，请人工确认后再处理"
            )
            mark_blocked(item, reason)
            issues.append(
                FaqImportIssue(
                    level="error",
                    sheet=item.sheet,
                    row=item.row,
                    field="提问示例",
                    message=reason,
                )
            )

    def _mark_file_question_conflicts(
        self,
        items: list[FaqImportPreviewItem],
        issues: list[FaqImportIssue],
    ) -> None:
        groups: dict[str, list[FaqImportPreviewItem]] = {}
        for item in items:
            groups.setdefault(normalize_text(item.standard_question), []).append(item)

        for group_items in groups.values():
            if len(group_items) <= 1:
                continue
            locations = "、".join(f"{item.sheet} 第 {item.row} 行" for item in group_items)
            for item in group_items:
                reason = f"同一 Excel 内标准问题重复：{locations}，默认跳过"
                mark_blocked(item, reason)
                issues.append(
                    FaqImportIssue(
                        level="error",
                        sheet=item.sheet,
                        row=item.row,
                        field="提问示例",
                        message=reason,
                    )
                )

    def _build_new_faq(
        self,
        *,
        item: FaqImportPreviewItem,
        status: int,
        updated_by: str,
        now: datetime,
    ) -> KbFaq:
        faq = KbFaq(
            knowledge_id=item.knowledge_id,
            version=1,
            created_by=updated_by,
            created_at=now,
            deleted_at=None,
        )
        self._apply_import_item(
            faq=faq,
            item=item,
            status=status,
            updated_by=updated_by,
            now=now,
            increment_version=False,
        )
        return faq

    def _apply_import_item(
        self,
        *,
        faq: KbFaq,
        item: FaqImportPreviewItem,
        status: int,
        updated_by: str,
        now: datetime,
        increment_version: bool = True,
    ) -> None:
        faq.category_l1 = item.category_l1
        faq.category_l2 = item.category_l2
        faq.category_l3 = item.category_l3
        faq.standard_question = item.standard_question
        faq.answer = item.answer
        faq.user_role = "common"
        faq.business_type = item.business_type
        faq.risk_level = item.risk_level
        faq.auth_required = item.auth_required
        faq.auto_answer = item.auto_answer
        faq.human_required = item.human_required
        faq.status = status
        faq.review_status = item.review_status
        faq.updated_by = updated_by
        faq.updated_at = now
        faq.embedding_status = 0
        faq.embedding_error = None
        faq.content_hash = hash_json(
            {
                "category_l1": item.category_l1,
                "category_l2": item.category_l2,
                "category_l3": item.category_l3,
                "standard_question": item.standard_question,
                "answer": item.answer,
                "user_role": "common",
                "business_type": item.business_type,
                "risk_level": item.risk_level,
                "auth_required": item.auth_required,
                "auto_answer": item.auto_answer,
                "human_required": item.human_required,
                "status": status,
            }
        )
        faq.embedding_input_hash = hash_json(
            {
                "categories": [item.category_l1, item.category_l2, item.category_l3],
                "question": item.standard_question,
                "paraphrases": item.paraphrases,
                "answer": item.answer,
            }
        )
        if increment_version:
            faq.version += 1

    def _parse_sheet(
        self,
        *,
        sheet: XlsxSheet,
        items: list[FaqImportPreviewItem],
        issues: list[FaqImportIssue],
        seen_questions: dict[str, tuple[str, int]],
        preview_limit: int,
    ) -> FaqImportSheetSummary:
        rows = sheet.rows
        if not rows:
            return FaqImportSheetSummary(
                sheet=sheet.name,
                total_rows=0,
                valid_rows=0,
                invalid_rows=0,
            )

        header_row_index = self._find_header_row(rows)
        if header_row_index is None:
            issues.append(
                FaqImportIssue(
                    level="error",
                    sheet=sheet.name,
                    message="未找到包含“提问示例”和“解答”的表头行",
                )
            )
            return FaqImportSheetSummary(
                sheet=sheet.name,
                total_rows=0,
                valid_rows=0,
                invalid_rows=0,
            )

        header_map = self._build_header_map(rows[header_row_index])
        total_rows = 0
        valid_rows = 0
        invalid_rows = 0

        for row_number, row in enumerate(rows[header_row_index + 1 :], start=header_row_index + 2):
            if not any(cell for cell in row):
                continue
            total_rows += 1

            question_text = get_cell(row, header_map.get("question"))
            answer = get_cell(row, header_map.get("answer"))
            if not question_text or not answer:
                invalid_rows += 1
                if not question_text:
                    issues.append(
                        FaqImportIssue(
                            level="error",
                            sheet=sheet.name,
                            row=row_number,
                            field="提问示例",
                            message="缺少提问示例，无法生成 FAQ",
                        )
                    )
                if not answer:
                    issues.append(
                        FaqImportIssue(
                            level="error",
                            sheet=sheet.name,
                            row=row_number,
                            field="解答",
                            message="缺少解答，无法生成 FAQ",
                        )
                    )
                continue

            question_parts = split_question_examples(question_text)
            standard_question = question_parts[0]
            paraphrases = unique_texts(question_parts[1:])
            category_l1 = get_cell(row, header_map.get("category_l1")) or sheet.name
            category_l2 = get_cell(row, header_map.get("category_l2"))
            category_l3 = get_cell(row, header_map.get("category_l3"))

            warnings: list[str] = []
            normalized_question = normalize_text(standard_question)
            if normalized_question in seen_questions:
                other_sheet, other_row = seen_questions[normalized_question]
                warning = f"标准问题与 {other_sheet} 第 {other_row} 行重复"
                warnings.append(warning)
                issues.append(
                    FaqImportIssue(
                        level="warning",
                        sheet=sheet.name,
                        row=row_number,
                        field="提问示例",
                        message=warning,
                    )
                )
            else:
                seen_questions[normalized_question] = (sheet.name, row_number)

            valid_rows += 1
            if len(items) < preview_limit:
                items.append(
                    FaqImportPreviewItem(
                        sheet=sheet.name,
                        row=row_number,
                        knowledge_id=build_import_knowledge_id(sheet.name, row_number),
                        category_l1=category_l1,
                        category_l2=category_l2,
                        category_l3=category_l3,
                        business_type=sheet.name,
                        standard_question=standard_question,
                        paraphrases=paraphrases,
                        answer=answer,
                        image_url=get_cell(row, header_map.get("image_url")),
                        warnings=warnings,
                    )
                )

        return FaqImportSheetSummary(
            sheet=sheet.name,
            total_rows=total_rows,
            valid_rows=valid_rows,
            invalid_rows=invalid_rows,
        )

    def _find_header_row(self, rows: list[list[str | None]]) -> int | None:
        for index, row in enumerate(rows[:10]):
            header_map = self._build_header_map(row)
            if "question" in header_map and "answer" in header_map:
                return index
        return None

    def _build_header_map(self, row: list[str | None]) -> dict[str, int]:
        result: dict[str, int] = {}
        generic_category_index: int | None = None
        for index, value in enumerate(row):
            normalized = normalize_header(value)
            if not normalized:
                continue
            if normalized == "分类":
                generic_category_index = index
                continue
            for field, aliases in HEADER_ALIASES.items():
                normalized_aliases = {normalize_header(alias) for alias in aliases}
                if normalized in normalized_aliases and field not in result:
                    result[field] = index
        if generic_category_index is not None:
            if "category_l2" in result:
                result.setdefault("category_l3", generic_category_index)
            else:
                result["category_l2"] = generic_category_index
        return result


def read_xlsx(content: bytes) -> list[XlsxSheet]:
    try:
        with ZipFile(BytesIO(content)) as archive:
            shared_strings = read_shared_strings(archive)
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            rels = read_workbook_relationships(archive)
            sheets: list[XlsxSheet] = []
            for sheet in workbook.findall(".//main:sheet", XML_NS):
                name = sheet.attrib["name"]
                relationship_id = sheet.attrib[f"{{{XML_NS['rel']}}}id"]
                target = rels[relationship_id]
                path = resolve_xlsx_path("xl/workbook.xml", target)
                rows = read_worksheet_rows(archive, path, shared_strings)
                sheets.append(XlsxSheet(name=name, rows=rows))
            return sheets
    except (BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise BusinessError(
            "Excel 文件解析失败，请确认上传的是有效的 .xlsx 文件",
            code="FAQ_IMPORT_PARSE_FAILED",
            status_code=400,
        ) from exc


def read_shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    result: list[str] = []
    for item in root.findall("main:si", XML_NS):
        texts = [node.text or "" for node in item.findall(".//main:t", XML_NS)]
        result.append("".join(texts))
    return result


def read_workbook_relationships(archive: ZipFile) -> dict[str, str]:
    root = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    return {
        node.attrib["Id"]: node.attrib["Target"]
        for node in root.findall("pkg_rel:Relationship", XML_NS)
    }


def read_worksheet_rows(
    archive: ZipFile,
    path: str,
    shared_strings: list[str],
) -> list[list[str | None]]:
    root = ElementTree.fromstring(archive.read(path))
    rows: list[list[str | None]] = []
    for row in root.findall(".//main:sheetData/main:row", XML_NS):
        values: list[str | None] = []
        for cell in row.findall("main:c", XML_NS):
            column_index = column_index_from_cell_ref(cell.attrib.get("r", "")) or len(values)
            while len(values) <= column_index:
                values.append(None)
            values[column_index] = read_cell_value(cell, shared_strings)
        rows.append(trim_trailing_empty(values))
    return rows


def read_cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> str | None:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        texts = [node.text or "" for node in cell.findall(".//main:t", XML_NS)]
        return normalize_cell("".join(texts))

    value_node = cell.find("main:v", XML_NS)
    if value_node is None or value_node.text is None:
        return None

    raw_value = value_node.text
    if cell_type == "s":
        index = int(raw_value)
        return normalize_cell(shared_strings[index] if index < len(shared_strings) else "")
    return normalize_cell(raw_value)


def resolve_xlsx_path(base_path: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return str(PurePosixPath(base_path).parent.joinpath(target))


def column_index_from_cell_ref(cell_ref: str) -> int | None:
    match = re.match(r"([A-Z]+)", cell_ref)
    if not match:
        return None
    result = 0
    for char in match.group(1):
        result = result * 26 + ord(char) - ord("A") + 1
    return result - 1


def trim_trailing_empty(values: list[str | None]) -> list[str | None]:
    while values and values[-1] is None:
        values.pop()
    return values


def normalize_cell(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).replace("\u00a0", " ").strip()
    return normalized or None


def normalize_header(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "").strip()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def get_cell(row: list[str | None], index: int | None) -> str | None:
    if index is None or index >= len(row):
        return None
    return row[index]


def split_question_examples(value: str) -> list[str]:
    parts = re.split(r"[\n\r；;]+", value)
    return unique_texts([part.strip(" \t，,。；;") for part in parts if part.strip()])


def unique_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_text(value)
        if normalized and normalized not in seen:
            result.append(value)
            seen.add(normalized)
    return result


def mark_blocked(item: FaqImportPreviewItem, reason: str) -> None:
    if reason not in item.blocking_reasons:
        item.blocking_reasons.append(reason)
    item.blocked = True


def build_import_knowledge_id(sheet_name: str, row_number: int) -> str:
    safe_sheet = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", sheet_name).strip("-")
    return f"IMPORT-{safe_sheet}-{row_number}"


def hash_json(value: object) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(serialized.encode("utf-8")).hexdigest()
