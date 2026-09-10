import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("stub_pages", ROOT / "scripts" / "29_stub_pages.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_rollup_sentence_associates_each_docket_with_its_following_disposition():
    lines = [
        "Cases 2010-01 through 2010-07 were Administratively Out of Order, and Cases "
        "2010-08 through 2010-14 were Judicially Out of Order."
    ]
    _, _, administrative = MODULE.find_disposition(lines, MODULE.variants("2010-07")[0], 0)
    _, _, judicial = MODULE.find_disposition(lines, MODULE.variants("2010-08")[0], 0)
    assert administrative == "Administratively Out of Order"
    assert judicial == "Judicially Out of Order"
