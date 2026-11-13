from fpdf import FPDF

from ..config import ROOT

FONTS = ROOT / "assets" / "fonts"
STATUS_RGB = {"evidenced": (46, 125, 50), "listed": (230, 140, 0), "related": (30, 100, 180), "missing": (150, 150, 150)}


class _Pdf(FPDF):
    def footer(self):
        self.set_y(-14)
        self.set_font("dv", "", 8)
        self.set_text_color(110)
        self.cell(0, 6, f"RecruitIQ review sheet. Page {self.page_no()}", align="C")


def build_pdf(ref: str, job_title: str, result: dict, status: str, decision_reason: str, identity: dict | None) -> bytes:
    pdf = _Pdf()
    pdf.add_font("dv", "", str(FONTS / "DejaVuSans.ttf"))
    pdf.add_font("dv", "B", str(FONTS / "DejaVuSans-Bold.ttf"))
    pdf.set_auto_page_break(True, 18)
    pdf.add_page()
    pdf.set_font("dv", "B", 16)
    pdf.cell(0, 9, f"Review sheet: {job_title}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("dv", "", 10)
    pdf.set_text_color(90)
    who = f"{identity['name']} ({identity['email']})" if identity else "identity hidden"
    pdf.cell(0, 6, f"Candidate {ref}   {who}   Status: {status}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)
    pdf.ln(3)
    pdf.set_font("dv", "B", 13)
    pdf.cell(0, 9, f"Match score {result['score']:.1f} / 100  ({result['band']})", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("dv", "", 9)
    pdf.set_text_color(90)
    pdf.multi_cell(0, 4.6, "An ordering aid for a person reading the application. It is not a hiring decision, and the weights "
                           "were chosen by hand, not learned from hiring outcomes.", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)
    pdf.ln(2)
    for k, v in result["components"].items():
        if v is not None:
            w = result["weights"].get(k, 0)
            pdf.cell(0, 5.5, f"{k.capitalize():12s} {v:5.1f}   (weight {w:.0%})", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    for title, items in (("Required skills", result["required"]), ("Preferred skills", result["preferred"])):
        if not items:
            continue
        pdf.set_font("dv", "B", 11)
        pdf.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        for it in items:
            pdf.set_font("dv", "B", 9)
            pdf.set_text_color(*STATUS_RGB[it["status"]])
            label = it["status"] + (f" via {it['via']}" if it.get("via") else "")
            pdf.cell(55, 5, f"{it['skill']}: {label}")
            pdf.set_text_color(0)
            pdf.set_font("dv", "", 8)
            ev = it["evidence"][0][:110] if it["evidence"] else ""
            pdf.cell(0, 5, ev, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
    yrs = result["years"]
    pdf.set_font("dv", "", 9)
    pdf.cell(0, 5.5, f"Work history from dates: {yrs['years']:g} years" + (f". Stated on the resume: {yrs['stated']:g}." if yrs.get("stated") else "."),
             new_x="LMARGIN", new_y="NEXT")
    for f in result["flags"]:
        pdf.set_text_color(160, 40, 40)
        pdf.multi_cell(0, 4.8, f"For the reviewer: {f['detail']}", new_x="LMARGIN", new_y="NEXT")
    for n in result["notes"]:
        pdf.set_text_color(90)
        pdf.multi_cell(0, 4.8, n, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)
    if decision_reason:
        pdf.ln(2)
        pdf.set_font("dv", "B", 10)
        pdf.cell(0, 6, "Reviewer's reason", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("dv", "", 9)
        pdf.multi_cell(0, 4.8, decision_reason, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
