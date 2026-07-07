"""Generate the Team Anvil demo solicitation PDF.

This one document drives the whole demo flow:
  - page 1 carries a seeded POC email + phone so the PII popup fires,
  - every mock obligation's verbatim_quote appears word-for-word on a known
    page, so quote verification and the Week-7 span highlight work for real.

Run from the repo root:  python3 data/make_demo_pdf.py
Outputs: data/samples/TeamAnvil-Demo-Solicitation.pdf
         frontend/public/samples/TeamAnvil-Demo-Solicitation.pdf
"""

from fpdf import FPDF

NAVY = (22, 50, 79)
MUTED = (81, 96, 111)

PAGES = {
    1: [
        ("h1", "SOLICITATION NO. W58RGZ-26-R-0042"),
        ("h2", "Enterprise Logistics Data Platform (ELDP)"),
        ("p", "Issued by: U.S. Army Contracting Command - Redstone Arsenal, AL"),
        ("p", "Notice type: Combined Synopsis/Solicitation. NAICS 541512."),
        ("p", "Posted: July 1, 2026. Response deadline: August 15, 2026, 2:00 PM ET."),
        ("gap", None),
        ("h3", "Point of Contact"),
        ("p", "Primary: John A. Merritt, Contract Specialist"),
        ("p", "Email: john.a.merritt.civ@army.mil"),
        ("p", "Phone: (256) 555-0142"),
        ("gap", None),
        ("h3", "Description"),
        ("p", "The Government intends to award a single Firm-Fixed-Price contract "
              "for the design, development, and sustainment of the Enterprise "
              "Logistics Data Platform. The platform will consolidate supply, "
              "maintenance, and transportation data into a single authoritative "
              "source for Army logistics decision-making."),
        ("p", "This is a total small business set-aside. The applicable clauses "
              "of the Federal Acquisition Regulation (FAR) and the Defense "
              "Federal Acquisition Regulation Supplement (DFARS) are "
              "incorporated as stated in Sections H and I of this solicitation."),
    ],
    2: [
        ("h1", "SECTION C - STATEMENT OF WORK"),
        ("h3", "C.1 Kickoff and Planning"),
        ("p", "The Contractor shall hold a program kickoff meeting within 10 "
              "business days after contract award. The kickoff shall cover the "
              "integrated master schedule, staffing plan, and risk register."),
        ("p", "The Contractor shall submit a Quality Control Plan within 15 days "
              "after contract award. The plan shall describe inspection "
              "procedures for each deliverable listed in Section F."),
        ("h3", "C.2 Design Deliverables"),
        ("p", "The Contractor shall deliver the System Design Document within 30 "
              "days after contract award. The document shall include the data "
              "architecture, interface control descriptions, and the security "
              "architecture aligned to the Army cloud reference design."),
        ("p", "All software developed under this contract shall be delivered "
              "with unlimited Government purpose rights unless otherwise "
              "negotiated prior to award."),
        ("h3", "C.3 Personnel"),
        ("p", "All Contractor personnel requiring access to Government systems "
              "shall complete cyber awareness training before access is granted. "
              "Evidence of completion shall be provided to the Contracting "
              "Officer's Representative."),
        ("p", "Key personnel substitutions require written approval from the "
              "Contracting Officer no fewer than 15 days in advance."),
    ],
    3: [
        ("h1", "SECTION F - DELIVERIES AND REPORTING"),
        ("h3", "F.1 Recurring Reports"),
        ("p", "The Contractor shall submit a Contract Status Report no later "
              "than the 15th day of each month. The report shall summarize "
              "technical progress, schedule status, and any issues requiring "
              "Government action."),
        ("p", "The Contractor shall conduct quarterly program management reviews "
              "at the Government facility. Slides are due 5 business days before "
              "each review."),
        ("h3", "F.2 Invoicing"),
        ("p", "The Contractor shall submit invoices electronically through Wide "
              "Area Workflow on a monthly basis. Invoices shall reference the "
              "contract line item number for each charge."),
        ("h3", "F.3 Transition"),
        ("p", "The Contractor shall provide a transition-out plan no later than "
              "90 days before contract completion, including knowledge transfer "
              "sessions and an inventory of Government property."),
    ],
    4: [
        ("h1", "SECTION H - SPECIAL CONTRACT REQUIREMENTS"),
        ("h3", "H.1 Safeguarding and Cyber Incident Reporting (DFARS 252.204-7012)"),
        ("p", "The Contractor shall provide adequate security on all covered "
              "contractor information systems in accordance with NIST SP 800-171."),
        ("p", "The Contractor shall rapidly report cyber incidents within 72 "
              "hours of discovery to the Department of Defense at "
              "https://dibnet.dod.mil. Reports shall include the incident report "
              "number assigned by DoD."),
        ("h3", "H.2 Cloud Computing (DFARS 252.239-7010)"),
        ("p", "The Contractor shall maintain FedRAMP Moderate authorization for "
              "all cloud services used in performance of this contract. Data "
              "shall remain within the United States unless otherwise authorized "
              "in writing."),
        ("h3", "H.3 Limitations on Subcontracting (FAR 52.219-14)"),
        ("p", "The Contractor shall not pay more than 50 percent of the amount "
              "paid by the Government for contract performance to subcontractors "
              "that are not similarly situated entities."),
        ("h3", "H.4 Organizational Conflicts of Interest"),
        ("p", "The Contractor shall disclose any actual or potential "
              "organizational conflict of interest within 5 days of discovery."),
    ],
    5: [
        ("h1", "SECTION L / M - INSTRUCTIONS AND EVALUATION"),
        ("h3", "L.1 Proposal Submission"),
        ("p", "Proposals are due no later than 2:00 PM Eastern Time on August "
              "15, 2026. Late proposals will not be considered."),
        ("p", "Technical proposals shall not exceed 25 pages, excluding the "
              "cover page, table of contents, and resumes."),
        ("p", "Offerors shall submit questions in writing no later than July 25, "
              "2026. Answers will be posted as an amendment on SAM.gov."),
        ("h3", "M.1 Basis of Award"),
        ("p", "The Government will evaluate proposals using a best value "
              "tradeoff between technical merit and price. Technical merit is "
              "significantly more important than price."),
        ("p", "Evaluation factors: Factor 1 - Technical Approach; Factor 2 - "
              "Past Performance; Factor 3 - Price. Offerors without relevant "
              "past performance will receive a neutral rating."),
    ],
}


class Doc(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, "W58RGZ-26-R-0042 - Enterprise Logistics Data Platform",
                  align="L", new_x="LMARGIN")
        self.cell(0, 6, f"Page {self.page_no()}", align="R",
                  new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 10, "Demo document generated for Team Anvil - not a real solicitation", align="C")


pdf = Doc(format="Letter")
pdf.set_auto_page_break(auto=True, margin=20)

for page_num in sorted(PAGES):
    pdf.add_page()
    for kind, text in PAGES[page_num]:
        if kind == "h1":
            pdf.set_font("Helvetica", "B", 15)
            pdf.set_text_color(*NAVY)
            pdf.multi_cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
        elif kind == "h2":
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(*NAVY)
            pdf.multi_cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
        elif kind == "h3":
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(*NAVY)
            pdf.multi_cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")
        elif kind == "p":
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(30, 30, 30)
            pdf.multi_cell(0, 5.5, text, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
        elif kind == "gap":
            pdf.ln(4)

for out in ("data/samples/TeamAnvil-Demo-Solicitation.pdf",
            "frontend/public/samples/TeamAnvil-Demo-Solicitation.pdf"):
    pdf.output(out)
    print("wrote", out)
