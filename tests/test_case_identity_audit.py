import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "78_audit_case_identities.py"
SPEC = importlib.util.spec_from_file_location("case_identity_audit", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def write_case(root: Path, name: str, text: str) -> None:
    cases = root / "cases"
    cases.mkdir(exist_ok=True)
    (cases / name).write_text(text, encoding="utf-8")


def test_top_of_body_caption_overrides_unsubstantiated_page_title(tmp_path: Path) -> None:
    write_case(
        tmp_path,
        "ga39_2011__stub_2010-14.md",
        """# 2010-14 — Sartorius v. Siouxlands Presbytery

### CASE NO. 2010-14

### MR. MICHAEL A. MCNEIL VS. CHESAPEAKE PRESBYTERY
""",
    )

    findings = MODULE.scan_case_page_identity(tmp_path)

    assert len(findings) == 1
    assert findings[0]["flags"] == ["case_page_body_caption_conflict"]
    assert "MICHAEL A. MCNEIL" in findings[0]["body_title"]
    assert "CHESAPEAKE PRESBYTERY" in findings[0]["body_title"]


def test_top_of_body_docket_detects_wrong_case_attached_to_page(tmp_path: Path) -> None:
    write_case(
        tmp_path,
        "ga39_2011__stub_2010-14.md",
        """# 2010-14 — Sartorius v. Siouxlands Presbytery

### CASE 2010-04 TE ART SARTORIUS ET AL. VS. SIOUXLANDS PRESBYTERY
""",
    )

    findings = MODULE.scan_case_page_identity(tmp_path)

    assert len(findings) == 1
    assert findings[0]["flags"] == ["case_page_body_docket_conflict"]
    assert findings[0]["body_case_id"] == "2010-04"


def test_later_citation_does_not_displace_first_body_caption(tmp_path: Path) -> None:
    write_case(
        tmp_path,
        "ga39_2011__2010-04.md",
        """# 2010-04 — Sartorius v. Siouxlands Presbytery

### CASE NO. 2010-04
### TE ART SARTORIUS ET AL. VS. SIOUXLANDS PRESBYTERY

The opinion later discusses another matter.
### CASE 2016-16 SARTORIUS VS. SIOUXLANDS PRESBYTERY
""",
    )

    assert MODULE.scan_case_page_identity(tmp_path) == []
