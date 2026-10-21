# Drawing File Organizer

도면 파일의 이름·리비전·내용 중복을 점검하고, 프로젝트별 폴더로 복사하는 Python 도구입니다.
원본을 변경하지 않으며 기본 실행은 보고서만 만드는 미리보기입니다.

## 구현 기능

- PDF·DWG·DXF 폴더 검색과 파일명 규칙 점검
- 숫자 리비전 비교, 도면·파일 형식별 최신 리비전 선택
- SHA256을 이용한 동일 내용 파일 확인
- 대소문자 차이·리비전 표기 차이에 따른 출력 경로 충돌 확인
- 프로젝트 / 분야 / 도면 번호별 복사
- CSV 목록과 브라우저에서 열 수 있는 HTML 보고서 생성
- 기존 파일 덮어쓰기 차단, 분석 후 원본 변경 감지, 복사 실패 시 새 파일 정리

## 실행

Python 3.12 이상이 필요합니다. 외부 패키지는 사용하지 않습니다.

파일명 규칙은 `프로젝트-분야-도면번호-R리비전.확장자`입니다.
예: `HOUSE-AR-A101-R01.pdf`, `만화카페-AR-A101-R02.dwg`.

```powershell
# 예제 DXF 다섯 개 생성
python examples/create_demo.py demo-input

# 실제 복사 없이 분류·검토 보고서 확인
python drawing_organizer.py demo-input demo-preview --latest-only

# 최신 리비전을 별도 폴더에 복사
python drawing_organizer.py demo-input demo-output --latest-only --apply
```

결과 예:

```text
demo-output/
  CAFE/AR/A101/CAFE-AR-A101-R01.dxf
  HOUSE/AR/A101/HOUSE-AR-A101-R01.dxf
  HOUSE/AR/A201/HOUSE-AR-A201-R01.dxf
  _reports/manifest.csv
  _reports/report.html
```

입력과 출력은 서로 포함되지 않는 폴더로 지정합니다.
규칙에 맞지 않는 파일은 보고서에 남기고 복사 대상에서 제외합니다. 내용이 같다는 이유만으로 서로 다른 도면 번호의 파일을 삭제하지 않습니다.
기존 출력 도면이 있으면 적용을 중단하므로 새 결과 폴더를 지정하세요.

## 점검 범위

파일명과 파일 단위의 내용 비교를 수행합니다. DWG·PDF 내부의 객체, 치수, 설계 적합성은 판독하지 않습니다.
예제는 직접 생성한 단순 DXF이며 실제 고객 도면이 아닙니다.

## 검증

```powershell
python -m unittest discover -s tests -v
```

리비전 선택, 경로 충돌, 원본 변경, 덮어쓰기 차단, 복사 실패 정리, 보고서 출력과 미리보기 동작을 검증합니다.

## 관련 프로젝트

- [건축 설계·CAD 포트폴리오](https://github.com/youns1998/portfolioCAD)
- [Revit BIM Inspector](https://github.com/youns1998/revit-bim-portfolio)
