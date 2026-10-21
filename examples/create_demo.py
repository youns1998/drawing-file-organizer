"""Create small valid DXF fixtures. They are examples, not client drawings."""
import sys
from pathlib import Path

target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("demo-input")
target.mkdir(parents=True, exist_ok=True)


def dxf(length: int) -> str:
    return f"0\nSECTION\n2\nENTITIES\n0\nLINE\n8\nWALL\n10\n0\n20\n0\n30\n0\n11\n{length}\n21\n0\n31\n0\n0\nENDSEC\n0\nEOF\n"


for name, length in [("HOUSE-AR-A101-R00.dxf", 5000), ("HOUSE-AR-A101-R01.dxf", 6000),
                     ("HOUSE-AR-A201-R01.dxf", 7000), ("CAFE-AR-A101-R01.dxf", 6000),
                     ("검토필요.dxf", 8000)]:
    path = target / name
    with path.open("x", encoding="ascii") as stream:
        stream.write(dxf(length))
print(f"DXF 예제 5개 생성: {target.resolve()}")
