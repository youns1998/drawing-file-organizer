"""Plan and copy drawing packages without changing the original files."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import os
import re
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED = {".pdf", ".dwg", ".dxf"}
NAME = re.compile(
    r"(?P<project>[A-Za-z0-9_가-힣]+)-(?P<discipline>[A-Za-z]{1,4})-"
    r"(?P<number>[A-Za-z]?\d{2,6})-R(?P<revision>\d{1,3})", re.IGNORECASE
)


@dataclass
class Drawing:
    source: Path
    relative_source: str
    project: str = ""
    discipline: str = ""
    number: str = ""
    revision: int = -1
    destination: str = ""
    digest: str = ""
    size: int = 0
    selected: bool = False
    issues: list[str] = field(default_factory=list)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def linked(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def analyze(source: Path, *, latest_only: bool = False) -> list[Drawing]:
    """Read filenames and hashes. Never open proprietary drawing contents for parsing."""
    source = source.resolve(strict=True)
    if not source.is_dir():
        raise ValueError("입력 경로는 폴더여야 합니다.")
    drawings: list[Drawing] = []

    def scan_error(error: OSError) -> None:
        raise error

    for folder, directories, names in os.walk(source, followlinks=False, onerror=scan_error):
        directories[:] = sorted(name for name in directories if not linked(Path(folder) / name))
        for name in sorted(names):
            path = Path(folder) / name
            if path.suffix.lower() not in SUPPORTED:
                continue
            row = Drawing(path, path.relative_to(source).as_posix())
            drawings.append(row)
            if linked(path):
                row.issues.append("링크 파일 제외")
                continue
            row.size = path.stat().st_size
            row.digest = file_hash(path)
            match = NAME.fullmatch(path.stem)
            if not match:
                row.issues.append("파일명 규칙 불일치")
                continue
            row.project = match["project"].upper()
            row.discipline = match["discipline"].upper()
            row.number = match["number"].upper()
            row.revision = int(match["revision"])
            filename = f"{row.project}-{row.discipline}-{row.number}-R{row.revision:02}{path.suffix.lower()}"
            row.destination = f"{row.project}/{row.discipline}/{row.number}/{filename}"
            row.selected = True

    groups: dict[tuple, list[Drawing]] = defaultdict(list)
    contents: dict[str, list[Drawing]] = defaultdict(list)
    for row in drawings:
        if row.selected:
            groups[(row.project, row.discipline, row.number, row.source.suffix.lower())].append(row)
        if row.digest:
            contents[row.digest].append(row)
    for group in groups.values():
        newest = max(row.revision for row in group)
        for row in group:
            if row.revision < newest:
                row.issues.append("이전 리비전")
                if latest_only:
                    row.selected = False
    for duplicates in contents.values():
        if len(duplicates) > 1:
            for row in duplicates:
                row.issues.append("동일 내용 파일 존재")
    destinations: dict[str, list[Drawing]] = defaultdict(list)
    for row in drawings:
        if row.selected:
            destinations[row.destination.casefold()].append(row)
    for duplicates in destinations.values():
        if len(duplicates) > 1:
            for row in duplicates:
                row.issues.append("출력 경로 충돌")
    return sorted(drawings, key=lambda row: row.relative_source.casefold())


def validate_output(source: Path, output: Path) -> Path:
    source, output = source.resolve(), output.resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("입력과 출력은 서로 포함되지 않는 별도 폴더로 지정하세요.")
    return output


def apply_plan(drawings: list[Drawing], output: Path) -> int:
    """Preflight everything, then copy exclusively; roll back only newly created files."""
    output = output.resolve()
    selected = [row for row in drawings if row.selected]
    for row in selected:
        if "출력 경로 충돌" in row.issues:
            raise ValueError("출력 경로 충돌이 있습니다. 미리보기 보고서를 확인하세요.")
        if not row.source.is_file() or linked(row.source) or file_hash(row.source) != row.digest:
            raise ValueError(f"분석 후 원본이 변경되었습니다: {row.relative_source}")
        target = output / row.destination
        if not target.resolve().is_relative_to(output):
            raise ValueError("출력 경로가 지정 폴더 밖을 가리킵니다.")
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"기존 파일은 덮어쓰지 않습니다: {target}")
    created: list[Path] = []
    try:
        for row in selected:
            target = output / row.destination
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.parent.resolve().is_relative_to(output):
                raise ValueError("출력 폴더에 외부 경로 링크가 있습니다.")
            with target.open("xb") as destination:
                created.append(target)
                with row.source.open("rb") as original:
                    shutil.copyfileobj(original, destination)
            if file_hash(target) != row.digest:
                raise ValueError(f"복사 중 원본 내용이 변경되었습니다: {row.relative_source}")
    except Exception:
        for target in reversed(created):
            target.unlink(missing_ok=True)
        raise
    return len(created)


def csv_cell(value: object) -> str:
    value = str(value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def write_reports(drawings: list[Drawing], output: Path, *, applied: bool) -> None:
    reports = output / "_reports"
    if not reports.resolve().is_relative_to(output.resolve()):
        raise ValueError("보고서 폴더가 출력 폴더 밖을 가리킵니다.")
    reports.mkdir(parents=True, exist_ok=True)
    for report_name in ("manifest.csv", "report.html"):
        if linked(reports / report_name):
            raise ValueError("보고서 경로에 링크 파일이 있습니다.")
    with (reports / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["원본", "프로젝트", "분야", "도면 번호", "리비전", "출력 경로", "선택", "검토 사항", "바이트", "SHA256"])
        for row in drawings:
            writer.writerow(map(csv_cell, [row.relative_source, row.project, row.discipline, row.number,
                row.revision if row.revision >= 0 else "", row.destination,
                "복사" if row.selected else "제외", " · ".join(row.issues), row.size, row.digest]))
    title = "도면 파일 정리 · " + ("복사 완료" if applied else "미리보기")
    rows = []
    for row in drawings:
        cells = [row.relative_source, row.destination or "—", "복사" if row.selected else "제외", " · ".join(row.issues) or "없음"]
        rows.append("<tr>" + "".join("<td>" + html.escape(cell) + "</td>" for cell in cells) + "</tr>")
    selected_count = sum(row.selected for row in drawings)
    report = f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>body{{font:16px/1.7 system-ui,sans-serif;color:#182421;background:#f5f7f3;max-width:1200px;margin:60px auto;padding:0 24px}}h1{{font-size:2rem}}.table{{overflow:auto;background:white;border:1px solid #dce3dd;border-radius:8px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:16px;text-align:left;border-bottom:1px solid #dce3dd;overflow-wrap:anywhere;min-width:100px}}th{{color:#526d5b}}.meta{{color:#526d5b;margin-bottom:32px}}footer{{margin-top:24px;color:#4f5e57;font-size:.85rem}}</style>
<h1>{title}</h1><p class="meta">대상 {len(drawings)}개 · 선택 {selected_count}개 · 검토 사항 포함 {sum(bool(row.issues) for row in drawings)}개</p>
<div class="table"><table><thead><tr><th>원본</th><th>정리 경로</th><th>처리</th><th>검토 사항</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<footer>파일명과 파일 내용을 비교한 결과입니다. DWG·PDF 내부 도면의 설계 적합성은 판정하지 않습니다.</footer></html>'''
    (reports / "report.html").write_text(report, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="도면 파일명·리비전·내용 중복 점검 및 폴더 정리")
    parser.add_argument("source", type=Path, help="원본 도면 폴더")
    parser.add_argument("output", type=Path, help="별도의 정리 결과 폴더")
    parser.add_argument("--latest-only", action="store_true", help="도면·파일 형식별 최신 리비전만 선택")
    parser.add_argument("--apply", action="store_true", help="미리보기 대신 실제 복사 실행")
    args = parser.parse_args(argv)
    try:
        output = validate_output(args.source, args.output)
        drawings = analyze(args.source, latest_only=args.latest_only)
        if args.apply:
            count = apply_plan(drawings, output)
            print(f"복사 완료: {count}개 (원본 유지)")
        else:
            print(f"미리보기: {sum(row.selected for row in drawings)}개 선택 / {len(drawings)}개 확인")
        write_reports(drawings, output, applied=args.apply)
        print(f"보고서: {output / '_reports' / 'report.html'}")
        return 0
    except (OSError, ValueError) as error:
        print(f"정리 중단: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
