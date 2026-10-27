"""Create the Daily Initial Flow Management checksheet template.

The template is intentionally unassigned: people are selected per record on the
My Forms screen. Running this script more than once leaves the existing
format untouched.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal, init_db
from app.models import User
from app.models_qms import QualityTeam, Format
from app.services import format_service as fmts

CODE = "QF-PQ-004"
TITLE = "Daily Initial Flow Management Control Items Monitoring Checksheet"


def layout() -> list[dict]:
    metadata = [
        {"label": "Part Name", "type": "text"},
        {"label": "Part No.", "type": "text"},
        {"label": "Model", "type": "text"},
        {"label": "Vendor", "type": "text"},
        {"label": "Date", "type": "date"},
    ]
    checklist = [
        {"label": "Gauge is within calibration", "required": False},
        {"label": "Work instruction is available at the station", "required": False},
    ]
    columns = [
        {"label": "S.NO", "type": "text", "readonly": True},
        {"label": "Stage", "type": "text", "readonly": True},
        {"label": "Control Items", "type": "text", "readonly": True},
        {"label": "Content / Spec", "type": "text", "readonly": True},
        {"label": "Checking Methods", "type": "text", "readonly": True},
        {"label": "Normal Frequency", "type": "text", "readonly": True},
        {"label": "IFM Frequency", "type": "text", "readonly": True},
    ]
    columns.extend(
        {"label": f"Day {day}", "type": "text"}
        for day in range(1, 32)
    )
    return [
        {
            "kind": "header",
            "title": "Daily initial flow management control items",
            "show_logo": True,
            "fields": metadata,
        },
        {
            "kind": "checklist",
            "title": "Before you start",
            "items": checklist,
        },
        {
            "kind": "table",
            "title": "Inspection rows and daily results",
            "columns": columns,
            "rows_mode": "fixed",
            "rows": [
                {"label": "1", "printed": {
                    "Stage": "Incoming Inspection",
                    "Control Items": "Faceplate",
                    "Content / Spec": "Free from defects - Scratches, Cracks, Sink Mark, Warpage, Weld lines, Gate mark, Painting Defects, peel off and Molding defects.",
                    "Checking Methods": "Visual Inspection",
                    "Normal Frequency": "As per sampling plan",
                    "IFM Frequency": "100%",
                }},
                {"label": "2", "printed": {
                    "Stage": "Incoming Inspection",
                    "Control Items": "CTP",
                    "Content / Spec": "Free from defects Sink Mark, Stress Mark, Black spot, Bright Spot, White spot, Dust, Printing Defects, CTP Icon defects. Free from light leakage.",
                    "Checking Methods": "Visual Inspection Tester",
                    "Normal Frequency": "As per sampling plan",
                    "IFM Frequency": "100%",
                }},
                {"label": "3", "printed": {
                    "Stage": "Incoming Inspection",
                    "Control Items": "Display",
                    "Content / Spec": "Free from defects such as black spot, White Spot, Bright spot, Dust etc.",
                    "Checking Methods": "Visual Inspection",
                    "Normal Frequency": "As per sampling plan",
                    "IFM Frequency": "100%",
                }},
                {"label": "4", "printed": {
                    "Stage": "Incoming Inspection",
                    "Control Items": "Sheet Metal part",
                    "Content / Spec": "Top Chassis; Bottom Chassis; Heat Sink.",
                    "Checking Methods": "Visual Inspection",
                    "Normal Frequency": "As per sampling plan",
                    "IFM Frequency": "100%",
                }},
                {"label": "5", "printed": {
                    "Stage": "Incoming Inspection",
                    "Control Items": "Top Chassis",
                    "Content / Spec": "Push out load checking; Torque checking of clinch nut; Anti rotating feature dimension checking; M5 Threading.",
                    "Checking Methods": "Load Tester; Torque wrench; Vernier Caliper; M5 Thread gauge",
                    "Normal Frequency": "2 Part / Lot",
                    "IFM Frequency": "1-5 / Lot; 2-5 / Lot; 3-5 / Lot; 4-5 / Lot",
                }},
                {"label": "6", "printed": {
                    "Stage": "Incoming Inspection",
                    "Control Items": "Bottom Chassis / Heat Sink",
                    "Content / Spec": "Check for damage, deformation, finish and fitment as per approved sample.",
                    "Checking Methods": "Visual Inspection",
                    "Normal Frequency": "As per sampling plan",
                    "IFM Frequency": "100%",
                }},
                {"label": "7", "printed": {
                    "Stage": "Product Inspection",
                    "Control Items": "FII",
                    "Content / Spec": "Gap between CTP and faceplate; Adhesion of CTP; Gap and flush on Gauge (Mounting Checking).",
                    "Checking Methods": "Filler Gauge; Height Gauge",
                    "Normal Frequency": "1 - 1 / Shift; 2 - 1 / Shift; 3 - 2 / day",
                    "IFM Frequency": "1 - 5 / Shift; 2 - 2 / Shift; 3 - 5 / day",
                }},
                {"label": "8", "printed": {
                    "Stage": "Product Inspection",
                    "Control Items": "Function Check - Assembly line",
                    "Content / Spec": "No issue allowed",
                    "Checking Methods": "EOL Station",
                    "Normal Frequency": "100%",
                    "IFM Frequency": "100%",
                }},
                {"label": "9", "printed": {
                    "Stage": "Product Inspection",
                    "Control Items": "Function Check - Firewall Station",
                    "Content / Spec": "No issue allowed",
                    "Checking Methods": "Firewall Testing Jig",
                    "Normal Frequency": "As per sampling plan",
                    "IFM Frequency": "100%",
                }},
                {"label": "10", "printed": {
                    "Stage": "Product Inspection",
                    "Control Items": "DIMENSION 1 / DIMENSION 2 / DIMENSION 3",
                    "Content / Spec": "178 ± 1; 112.5 ± 0.4 (SIZE); 4 X 3.0 ± 0.1",
                    "Checking Methods": "Measure",
                    "Normal Frequency": "",
                    "IFM Frequency": "",
                }},
                {"label": "11", "printed": {
                    "Stage": "Product Inspection",
                    "Control Items": "Nuts Presence in Silver box",
                    "Content / Spec": "6X M5X0.8 TAP",
                    "Checking Methods": "Visual Inspection",
                    "Normal Frequency": "N=2 at start of shift; N=2 at end of shift",
                    "IFM Frequency": "N=4 at start of shift; N=4 at end of shift",
                }},
                {"label": "12", "printed": {
                    "Stage": "Product Inspection",
                    "Control Items": "DIMENSION 5 / Gap 6 / Flush 7",
                    "Content / Spec": "198.4 ± 0.4; 0.3 ± 0.2; 0.48 ± 0.25",
                    "Checking Methods": "Measure",
                    "Normal Frequency": "",
                    "IFM Frequency": "",
                }},
                {"label": "13", "printed": {
                    "Stage": "Product Inspection",
                    "Control Items": "Checking Fixture - Gap / Flush",
                    "Content / Spec": "0.1 to 0.5; +/- 0.3",
                    "Checking Methods": "Measure (Filler Gauge); Measure (Dial Gauge)",
                    "Normal Frequency": "N=1 at start of shift; N=1 at end of shift",
                    "IFM Frequency": "N=2 at start of shift; N=2 at end of shift",
                }},
                {"label": "14", "printed": {
                    "Stage": "Product Inspection",
                    "Control Items": "Top Chassis",
                    "Content / Spec": "Push out load checking; Torque checking of clinch nut; Anti rotating feature dimension checking; M5 Threading",
                    "Checking Methods": "Load Tester; Torque wrench; Vernier Caliper; M5 Thread gauge",
                    "Normal Frequency": "2 Part / Lot",
                    "IFM Frequency": "1 - 5 / Lot; 2 - 5 / Lot; 3 - 5 / Lot; 4 - 5 / Lot",
                }},
                {"label": "15", "printed": {
                    "Stage": "Product Inspection",
                    "Control Items": "CTP",
                    "Content / Spec": "CTP Symbol Checking; CTP Push out load checking; Visual Inspection as per inspection standard.",
                    "Checking Methods": "Trace paper; Push out tester",
                    "Normal Frequency": "2 Part / Lot",
                    "IFM Frequency": "1 - 5 part / Lot; 2 - 5 part / Lot; 3 - 100%",
                }},
                {"label": "16", "printed": {
                    "Stage": "Product Inspection",
                    "Control Items": "Assembly Condition",
                    "Content / Spec": "Free from wrong, loose and missing parts; free from floating screw; label as per drawing.",
                    "Checking Methods": "Visual Inspection",
                    "Normal Frequency": "100%",
                    "IFM Frequency": "100%",
                }},
                {"label": "17", "printed": {
                    "Stage": "Product Inspection",
                    "Control Items": "Connector Pin condition / MRT Label / Screw quantity / Warranty label",
                    "Content / Spec": "No damage, bend or loss material; correct description; screws assembled properly; no visual defect.",
                    "Checking Methods": "Visual inspection at Final Inspection; Vision System to verify",
                    "Normal Frequency": "1 - 100%; 2 - 100%; 3 - 100%; 4 - 100%",
                    "IFM Frequency": "1 - 100%; 2 - 100%; 3 - 100%; 4 - 100%",
                }},
            ],
        },
        {
            "kind": "note",
            "title": "Instructions",
            "body": "Record the result for each inspection row and day. Enter remarks in the field help or notes where required.",
        },
    ]


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        existing = db.query(Format).filter(Format.code == CODE).first()
        if existing:
            # This is a bundled starter template. Refresh only its layout so an
            # earlier generic version becomes the checksheet shown in the workbook.
            data = {"layout": layout()}
            fmts._apply_layout(db, existing, data)
            fmts._apply_fields(db, existing, data["fields"], replace=True)
            db.commit()
            print(f"Updated: {existing.code} rev {existing.revision} ({existing.status})")
            return 0

        team = db.query(QualityTeam).filter(QualityTeam.code == "PQ").first()
        if not team:
            fmts.ensure_teams(db)
            team = db.query(QualityTeam).filter(QualityTeam.code == "PQ").first()
        admin = db.query(User).filter(User.is_admin.is_(True)).first()
        if not team or not admin:
            raise RuntimeError("A Process Quality team and administrator are required.")

        created = fmts.create_format(db, admin, {
            "code": CODE,
            "title": TITLE,
            "description": "Daily checksheet with six inspection rows and 31 daily result columns.",
            "team_id": team.id,
            "frequency": "daily",
            "work_instruction": "Complete the metadata, confirm the pre-start checks, then record each inspection row across the applicable day columns.",
            "storage_path": "Records / Process Quality / QF-PQ-004",
            "layout": layout(),
        })
        fmts.activate(db, created, admin)
        print(f"Created and released: {created.code} rev {created.revision} - {created.title}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
