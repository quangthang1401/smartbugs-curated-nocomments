"""
report_builder.py
─────────────────
Đọc audit_results.json → xuất smartbugs_final_report.xlsx
- Bỏ cột Accuracy (%)
- Ô tổng TP/FP/Accuracy ở sheet Summary
"""

import json
import os
import re
import pandas as pd
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

RESULTS_JSON    = "audit_results.json"
REPORT_FILENAME = "smartbugs_final_report.xlsx"

_ALIASES = {
    "unchecked low level calls":  "unchecked low level calls",
    "unchecked low-level calls":  "unchecked low level calls",
    "unchecked_low_level_calls":  "unchecked low level calls",
    "unchecked low level call":   "unchecked low level calls",
    "unchecked low calls":        "unchecked low level calls",
    "reentrancy":                 "reentrancy",
    "re-entrancy":                "reentrancy",
    "bad randomness":             "bad randomness",
    "time manipulation":          "time manipulation",
    "arithmetic":                 "arithmetic",
    "access control":             "access control",
    "denial of service":          "denial of service",
    "dos":                        "denial of service",
    "front running":              "front running",
    "front-running":              "front running",
    "short addresses":            "short addresses",
    "short address":              "short addresses",
    "clean":                      "clean",
    "other":                      "other",
}

def normalize(vuln: str) -> str:
    return _ALIASES.get(vuln.lower().strip(), vuln.lower().strip())


def build_report():
    if not os.path.exists(RESULTS_JSON):
        print(f"❌ Không tìm thấy {RESULTS_JSON}. Hãy chạy main_auditor.py trước.")
        return

    with open(RESULTS_JSON, "r", encoding="utf-8") as f:
        results = json.load(f)

    results.sort(key=lambda x: x.get("order", 9999))

    total   = len(results)
    correct = 0
    rows    = []

    for idx, r in enumerate(results, start=1):
        gt_vul  = r.get("gt_vul",  "Unknown")
        llm_vul = r.get("llm_vul", "Unknown")

        is_tp = normalize(gt_vul) == normalize(llm_vul)
        if is_tp:
            correct += 1

        gt_lines = r.get("gt_lines", [])
        label_line = ", ".join(str(l) for l in gt_lines) if gt_lines else "N/A"

        rows.append({
            "STT":        idx,
            "Address":    r.get("address",  ""),
            "Name":       r.get("filename", ""),
            "Label Vul":  gt_vul,
            "Label Line": label_line,
            "LLM Vul":    llm_vul,
            "LLM Line":   r.get("llm_line", "N/A"),
            "TP/FP":      "TP" if is_tp else "FP",
            "Reasoning":  r.get("reasoning", ""),
        })

    df = pd.DataFrame(rows)

    # ── Styles ───────────────────────────────────────────────────────────────
    HDR_FILL  = PatternFill(start_color="1F3864", end_color="1F3864", fill_type="solid")
    HDR_FONT  = Font(color="FFFFFF", bold=True, size=10)
    HDR_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)

    TP_FILL   = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    TP_FONT   = Font(color="276221", bold=True)
    FP_FILL   = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    FP_FONT   = Font(color="9C0006", bold=True)

    SUM_FILL  = PatternFill(start_color="FFE699", end_color="FFE699", fill_type="solid")
    SUM_FONT  = Font(bold=True, size=10)
    CENTER    = Alignment(horizontal="center", vertical="center")
    WRAP_TOP  = Alignment(wrap_text=True, vertical="top")

    thin = Side(style="thin", color="BFBFBF")
    BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)

    col_widths = {
        "A": 5,   # STT
        "B": 20,  # Address
        "C": 30,  # Name
        "D": 22,  # Label Vul
        "E": 15,  # Label Line
        "F": 22,  # LLM Vul
        "G": 10,  # LLM Line
        "H": 7,   # TP/FP
        "I": 65,  # Reasoning
    }

    accuracy = round(correct / total * 100, 2) if total else 0
    fp_count = total - correct

    with pd.ExcelWriter(REPORT_FILENAME, engine="openpyxl") as writer:

        # ══ Sheet 1: Audit Results ══════════════════════════════════════════
        df.to_excel(writer, index=False, sheet_name="Audit Results")
        ws = writer.sheets["Audit Results"]

        # Header style
        for cell in ws[1]:
            cell.fill      = HDR_FILL
            cell.font      = HDR_FONT
            cell.alignment = HDR_ALIGN
            cell.border    = BORDER

        ws.row_dimensions[1].height = 28

        # Data rows
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
            for cell in row:
                cell.border    = BORDER
                cell.alignment = CENTER

            tp_fp_cell = row[7]   # cột H
            if tp_fp_cell.value == "TP":
                tp_fp_cell.fill = TP_FILL
                tp_fp_cell.font = TP_FONT
            elif tp_fp_cell.value == "FP":
                tp_fp_cell.fill = FP_FILL
                tp_fp_cell.font = FP_FONT

            # Reasoning: wrap text, left-align
            row[8].alignment = WRAP_TOP
            ws.row_dimensions[row[0].row].height = 50

        # Column widths
        for col, w in col_widths.items():
            ws.column_dimensions[col].width = w

        # Freeze header row
        ws.freeze_panes = "A2"

        # ── Summary block ở góc phải bên trên (cột K-L) ─────────────────────
        summary = [
            ("Total Files",    total),
            ("TP (Correct)",   correct),
            ("FP (Wrong)",     fp_count),
            ("Accuracy (%)",   f"{accuracy}%"),
        ]

        start_row = 1
        for i, (label, value) in enumerate(summary):
            label_cell = ws.cell(row=start_row + i, column=11, value=label)   # K
            value_cell = ws.cell(row=start_row + i, column=12, value=value)   # L

            label_cell.fill      = SUM_FILL
            label_cell.font      = SUM_FONT
            label_cell.alignment = CENTER
            label_cell.border    = BORDER

            value_cell.font      = SUM_FONT
            value_cell.alignment = CENTER
            value_cell.border    = BORDER

            # TP dòng xanh, FP dòng đỏ
            if label == "TP (Correct)":
                value_cell.fill = TP_FILL
                value_cell.font = Font(color="276221", bold=True)
            elif label == "FP (Wrong)":
                value_cell.fill = FP_FILL
                value_cell.font = Font(color="9C0006", bold=True)

        ws.column_dimensions["K"].width = 16
        ws.column_dimensions["L"].width = 12

    # ── Console summary ───────────────────────────────────────────────────────
    print(f"\n{'='*45}")
    print(f"  📊 AUDIT SUMMARY")
    print(f"{'='*45}")
    print(f"  Total files  : {total}")
    print(f"  TP (correct) : {correct}")
    print(f"  FP (wrong)   : {fp_count}")
    print(f"  Accuracy     : {accuracy}%")
    print(f"{'='*45}")
    print(f"  ✅ Report: {REPORT_FILENAME}\n")


if __name__ == "__main__":
    build_report()