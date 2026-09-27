"""Printable PDF documents (sales invoices) rendered with ReportLab."""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models.organization import Company
from app.models.sales import InvoiceStatus, SalesInvoice


def _fmt(value: Decimal) -> str:
    return f"{value:,.2f}"


def _qty(value: Decimal) -> str:
    text = f"{value:,.3f}".rstrip("0").rstrip(".")
    return text or "0"


def _p(text: str | None, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(text or "").replace("\n", "<br/>"), style)


def render_invoice_pdf(invoice: SalesInvoice, company: Company | None, footer: str) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Invoice {invoice.invoice_number or 'DRAFT'}",
        author=company.name if company else "",
    )
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    small = ParagraphStyle("small", parent=normal, fontSize=8, leading=10)
    heading = ParagraphStyle("heading", parent=styles["Title"], alignment=2, fontSize=20)
    bold = ParagraphStyle("bold", parent=normal, fontName="Helvetica-Bold")

    story = []

    # Header: company on the left, document title on the right.
    company_lines = []
    if company:
        company_lines = [
            company.legal_name or company.name,
            company.address or "",
            ", ".join(x for x in (company.city, company.country) if x),
            f"TPIN: {company.tpin}" if company.tpin else "",
            f"VAT: {company.vat_number}" if company.vat_number else "",
            " | ".join(x for x in (company.phone, company.email) if x),
        ]
    title = "TAX INVOICE" if invoice.status != InvoiceStatus.DRAFT else "DRAFT INVOICE"
    if invoice.status == InvoiceStatus.CANCELLED:
        title = "CANCELLED INVOICE"
    header = Table(
        [
            [
                _p("\n".join(line for line in company_lines if line), normal),
                Paragraph(title, heading),
            ]
        ],
        colWidths=[100 * mm, 74 * mm],
    )
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [header, Spacer(1, 8 * mm)]

    customer = invoice.customer
    bill_to = "\n".join(
        x
        for x in (
            customer.name,
            customer.address or "",
            customer.city or "",
            f"TPIN: {customer.tpin}" if customer.tpin else "",
        )
        if x
    )
    meta = [
        ["Invoice no.", invoice.invoice_number or "DRAFT"],
        ["Invoice date", invoice.invoice_date.isoformat()],
        ["Due date", invoice.due_date.isoformat()],
        ["Currency", invoice.currency],
    ]
    if invoice.customer_reference:
        meta.append(["Your ref.", invoice.customer_reference])
    parties = Table(
        [
            [_p("Bill to", bold), ""],
            [_p(bill_to, normal), Table(meta, colWidths=[28 * mm, 42 * mm])],
        ],
        colWidths=[104 * mm, 70 * mm],
    )
    parties.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [parties, Spacer(1, 8 * mm)]

    rows = [["#", "Description", "Qty", "Unit price", "Disc %", "VAT %", "Amount"]]
    for line in invoice.lines:
        rows.append(
            [
                str(line.line_no),
                _p(line.description, small),
                _qty(line.quantity),
                _fmt(line.unit_price),
                _fmt(line.discount_percent),
                _fmt(line.tax_rate),
                _fmt(line.line_subtotal),
            ]
        )
    table = Table(
        rows,
        colWidths=[8 * mm, 70 * mm, 16 * mm, 24 * mm, 16 * mm, 16 * mm, 24 * mm],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3b57")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#cccccc")),
            ]
        )
    )
    story += [table, Spacer(1, 6 * mm)]

    totals = [
        ["Subtotal", _fmt(invoice.subtotal)],
        ["Discount", _fmt(invoice.discount_total)],
        ["VAT", _fmt(invoice.tax_total)],
        [f"Total ({invoice.currency})", _fmt(invoice.total)],
        ["Paid", _fmt(invoice.amount_paid)],
        ["Balance due", _fmt(invoice.balance_due)],
    ]
    totals_table = Table(totals, colWidths=[40 * mm, 30 * mm], hAlign="RIGHT")
    totals_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("FONTNAME", (0, 3), (-1, 3), "Helvetica-Bold"),
                ("FONTNAME", (0, 5), (-1, 5), "Helvetica-Bold"),
                ("LINEABOVE", (0, 3), (-1, 3), 0.5, colors.black),
            ]
        )
    )
    story += [totals_table, Spacer(1, 10 * mm)]
    if invoice.notes:
        story += [_p(invoice.notes, small), Spacer(1, 4 * mm)]
    if footer:
        story.append(_p(footer, small))

    doc.build(story)
    return buffer.getvalue()
