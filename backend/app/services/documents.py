"""Printable quotations and invoices (ReportLab), laid out like Nyangu's own documents.

Layout: logo on top; company details left, document title centre, tax details right; the
customer ("To:"); a row of reference boxes (Account, Date, Order No, Delivery Note, Our
Reference); the item lines; and, at the foot of the last page, signature lines on the left and
totals on the right. Pages are numbered "Page x of y" and stamped with the print time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    Flowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.config import get_settings
from app.models.organization import Company
from app.models.sales import InvoiceStatus, Quotation, SalesInvoice
from app.utils.money import ZERO
from app.utils.time import business_tz, utcnow

NAVY = colors.HexColor("#1f2d7a")
GREY = colors.HexColor("#6b6b6b")
LINK = colors.HexColor("#1a4fd6")
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 14 * mm
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN

DEFAULT_LOGO = Path(__file__).resolve().parent.parent / "assets" / "logo.jpg"


def logo_path() -> Path | None:
    configured = get_settings().COMPANY_LOGO_PATH
    path = Path(configured) if configured else DEFAULT_LOGO
    return path if path.is_file() else None


# ---------------------------------------------------------------------- styles and formatting
def _style(name: str, **kw: object) -> ParagraphStyle:
    base = {"fontName": "Helvetica", "fontSize": 9, "leading": 11.5}
    base.update(kw)
    return ParagraphStyle(name, **base)  # type: ignore[arg-type]


S = {
    "company": _style("company", fontName="Helvetica-Bold", fontSize=11, leading=14),
    "body": _style("body", fontSize=9.5, leading=13.5),
    "title": _style(
        "title",
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=NAVY,
        alignment=TA_CENTER,
    ),
    "label": _style("label", fontSize=9.5, leading=13),
    "value": _style("value", fontName="Helvetica-Bold", fontSize=9.5, leading=13),
    "to": _style("to", fontName="Helvetica-Bold", fontSize=9.5, leading=11.5),
    "box_head": _style("box_head", fontName="Helvetica-Bold", fontSize=9.5, alignment=TA_CENTER),
    "box": _style("box", fontSize=9.5, alignment=TA_CENTER),
    "th": _style("th", fontName="Helvetica-Bold", fontSize=8.5, leading=10),
    "th_r": _style("th_r", fontName="Helvetica-Bold", fontSize=8.5, leading=10, alignment=TA_RIGHT),
    "td": _style("td", fontSize=8.5, leading=10),
    "td_r": _style("td_r", fontSize=8.5, leading=10, alignment=TA_RIGHT),
    "small": _style("small", fontSize=8, leading=10, textColor=GREY),
    "tot": _style("tot", fontSize=9.5, leading=12),
    "tot_r": _style("tot_r", fontSize=9.5, leading=12, alignment=TA_RIGHT),
    "tot_b": _style("tot_b", fontName="Helvetica-Bold", fontSize=9.5, leading=12),
    "tot_b_r": _style(
        "tot_b_r", fontName="Helvetica-Bold", fontSize=9.5, leading=12, alignment=TA_RIGHT
    ),
    "grand": _style("grand", fontName="Helvetica-Bold", fontSize=12.5, leading=15),
    "grand_r": _style(
        "grand_r", fontName="Helvetica-Bold", fontSize=12.5, leading=15, alignment=TA_RIGHT
    ),
}


def money_text(value: Decimal | None) -> str:
    return f"{(value or ZERO):,.2f}"


def qty_text(value: Decimal) -> str:
    text = f"{value:,.3f}".rstrip("0").rstrip(".")
    return text or "0"


def date_text(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else ""


def printed_at() -> str:
    now = utcnow().astimezone(business_tz())
    return f"{now:%d/%m/%Y} {now.hour % 12 or 12}:{now:%M:%S %p}"


def para(text: str | None, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(text or "").replace("\n", "<br/>"), style)


# ---------------------------------------------------------------------- page furniture
class NumberedCanvas(rl_canvas.Canvas):
    """Draws "Page x of y" (top right) and the print time (bottom right) on every page."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._saved_pages: list[dict] = []
        self._stamp = printed_at()

    def showPage(self) -> None:  # noqa: N802 - ReportLab API
        self._saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._saved_pages)
        for state in self._saved_pages:
            self.__dict__.update(state)
            self.setFont("Helvetica", 8)
            self.setFillColor(GREY)
            self.drawRightString(
                PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 10 * mm, f"Page {self._pageNumber} of {total}"
            )
            self.drawRightString(PAGE_WIDTH - MARGIN, 7 * mm, self._stamp)
            super().showPage()
        super().save()


class AtPageBottom(Flowable):
    """Places its content at the bottom of the current page (or the next, if it does not fit)."""

    def __init__(self, content: Flowable) -> None:
        super().__init__()
        self.content = content
        self._content_height = 0.0

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        _, self._content_height = self.content.wrap(avail_width, avail_height)
        # Asking for more than is available moves the block to a fresh page.
        return avail_width, max(avail_height, self._content_height)

    def draw(self) -> None:
        self.content.drawOn(self.canv, 0, 0)


# ---------------------------------------------------------------------- document model
@dataclass
class DocumentView:
    title: str
    number: str
    doc_date: date
    customer_code: str
    customer_lines: list[str]
    order_no: str
    prices_include_tax: bool
    lines: list
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    total: Decimal
    left_rows: list[tuple[str, str]]
    extra_totals: list[tuple[str, Decimal]]
    notes: str | None


def _customer_lines(customer) -> list[str]:  # noqa: ANN001
    lines = [customer.name]
    if customer.address:
        lines.extend(line.strip() for line in customer.address.splitlines() if line.strip())
    if customer.city:
        lines.append(customer.city)
    if customer.tpin:
        lines.append(f"TPIN: {customer.tpin}")
    return [line.upper() for line in lines]


def _payment_terms(customer) -> str:  # noqa: ANN001
    days = customer.payment_terms_days
    return "Cash / immediate" if not days else f"{days} days"


def _tax_header(lines: list) -> str:
    rates = {Decimal(line.tax_rate) for line in lines}
    if len(rates) == 1:
        rate = rates.pop()
        return f"Tax {rate.normalize():f}%"
    return "Tax"


# ---------------------------------------------------------------------- building blocks
def _logo() -> Flowable | None:
    path = logo_path()
    if not path:
        return None
    reader = ImageReader(str(path))
    width, height = reader.getSize()
    target_height = 30 * mm
    image = Image(str(path), width=target_height * width / height, height=target_height)
    image.hAlign = "CENTER"
    return image


def _header(company: Company | None, view: DocumentView) -> list[Flowable]:
    name = (company.legal_name or company.name) if company else "Nyangu Holdings"
    address_parts = []
    if company and company.address:
        address_parts.append(company.address)
    if (
        company
        and company.city
        and (not company.address or company.city.lower() not in company.address.lower())
    ):
        address_parts.append(", ".join(x for x in (company.city, company.country) if x))

    left = [para(name.upper(), S["company"]), Spacer(1, 2)]
    left += [para(part, S["body"]) for part in address_parts]

    def row(label: str, value: str | None, style: ParagraphStyle = S["value"]) -> list:
        return [para(label, S["label"]), para(value or "", style)]

    details = []
    if company:
        # Only print the details that are filled in on the company profile.
        if company.tpin:
            details.append(row("TPIN:", company.tpin))
        if company.vat_number or company.tpin:
            details.append(row("VAT Registration:", company.vat_number or company.tpin))
        if company.phone:
            details.append(row("Telephone:", company.phone, S["label"]))
        if company.email:
            details.append(["", ""])
            email = escape(company.email)
            details.append(
                [
                    para("Email:", S["label"]),
                    Paragraph(
                        f'<u><a href="mailto:{email}" color="#1a4fd6">{email}</a></u>',
                        _style("email", fontSize=9, leading=13),
                    ),
                ]
            )
    right = Table(details, colWidths=[27.5 * mm, 38 * mm]) if details else Spacer(1, 1)
    if details:
        right.setStyle(
            TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ]
            )
        )

    # Longer titles ("Cancelled Invoice") get a smaller font so they stay in their column.
    title_style = (
        S["title"]
        if len(view.title) <= 9
        else _style(
            "title_small",
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=NAVY,
            alignment=TA_CENTER,
        )
    )
    top = Table(
        [[left, para(view.title, title_style), right]],
        colWidths=[CONTENT_WIDTH * 0.40, CONTENT_WIDTH * 0.24, CONTENT_WIDTH * 0.36],
    )
    top.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (1, 0), (1, 0), 6),
            ]
        )
    )

    to_block = [para("To:", S["to"])] + [para(line, S["to"]) for line in view.customer_lines]
    tax_flag = para(
        f"TaxInclusive  {'True' if view.prices_include_tax else 'False'}",
        _style("flag", fontSize=11, leading=13),
    )
    to_row = Table([[to_block, tax_flag]], colWidths=[CONTENT_WIDTH * 0.64, CONTENT_WIDTH * 0.36])
    to_row.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (0, 0), "TOP"),
                ("VALIGN", (1, 0), (1, 0), "BOTTOM"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return [top, Spacer(1, 1 * mm), to_row, Spacer(1, 5 * mm)]


def _reference_boxes(view: DocumentView) -> Table:
    heads = ["Account", "Date", "Order No", "Delivery Note", "Our Reference"]
    values = [view.customer_code, date_text(view.doc_date), view.order_no, "", view.number]
    table = Table(
        [[para(h, S["box_head"]) for h in heads], [para(v, S["box"]) for v in values]],
        colWidths=[CONTENT_WIDTH / 5] * 5,
    )
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 1), (-1, 1), 2),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 2),
    ]
    for col in range(5):
        style.append(("BOX", (col, 1), (col, 1), 0.8, colors.black))
    table.setStyle(TableStyle(style))
    return table


def _items(view: DocumentView) -> Table:
    price_head = "Price (In)" if view.prices_include_tax else "Price (Ex)"

    def head(label: str, style: ParagraphStyle) -> Paragraph:
        return Paragraph(f"<u>{escape(label)}</u>", style)

    header = [
        head("Item Code", S["th"]),
        head("Item Description", S["th"]),
        head("Quantity", S["th_r"]),
        head("Unit", S["th"]),
        head(price_head, S["th_r"]),
        head("Disc %", S["th_r"]),
        head(_tax_header(view.lines), S["th_r"]),
        head("Tax Incl", S["th_r"]),
    ]
    rows = [header]
    for line in view.lines:
        discount = Decimal(line.discount_percent)
        rows.append(
            [
                para(line.product.sku, S["td"]),
                para(line.description, S["td"]),
                para(qty_text(Decimal(line.quantity)), S["td_r"]),
                para(line.product.unit, S["td"]),
                para(money_text(line.unit_price), S["td_r"]),
                para(f"{discount.normalize():f}" if discount else "", S["td_r"]),
                para(money_text(line.line_tax), S["td_r"]),
                para(money_text(line.line_total), S["td_r"]),
            ]
        )
    widths = [20, 58, 18, 12, 22, 15, 21, 23]  # mm, scaled to the content width
    scale = CONTENT_WIDTH / (sum(widths) * mm)
    table = Table(rows, colWidths=[w * mm * scale for w in widths], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 0.6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0.6),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
            ]
        )
    )
    return table


def _footer_block(view: DocumentView, footer_text: str | None) -> Table:
    dashes = "_ " * 22

    def sign_row(label: str, value: str) -> list:
        text = value if value else dashes
        return [
            para(label, S["tot"]),
            para(text, _style("dash", fontSize=9, textColor=GREY if not value else colors.black)),
        ]

    left = Table(
        [sign_row(label, value) for label, value in view.left_rows], colWidths=[27 * mm, 72 * mm]
    )
    left.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ]
        )
    )

    tax_label = _tax_header(view.lines).replace("Tax ", "Tax  ") if view.lines else "Tax"
    totals = [
        [para("Total (Excl)", S["tot"]), para(money_text(view.subtotal), S["tot_r"])],
        [para(tax_label, S["tot"]), para(money_text(view.tax_total), S["tot_r"])],
        [para("Total (Incl)", S["tot_b"]), para(money_text(view.total), S["tot_b_r"])],
        [para("Discount", S["tot"]), para(money_text(view.discount_total), S["tot_r"])],
        [para("Rounding", S["tot"]), para(money_text(ZERO), S["tot_r"])],
        [para("Total (Incl)", S["grand"]), para(money_text(view.total), S["grand_r"])],
    ]
    for label, amount in view.extra_totals:
        totals.append([para(label, S["tot_b"]), para(money_text(amount), S["tot_b_r"])])
    right = Table(totals, colWidths=[45 * mm, 34 * mm])
    right.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5),
                ("LINEBELOW", (0, 4), (-1, 4), 0.8, colors.black),
                ("TOPPADDING", (0, 5), (-1, 5), 4),
            ]
        )
    )

    body = Table([[left, right]], colWidths=[CONTENT_WIDTH - 82 * mm, 82 * mm])
    body.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEABOVE", (0, 0), (-1, 0), 0.8, colors.black),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    rows = []
    if view.notes:
        rows.append([para(view.notes, S["small"])])
    rows.append([body])
    if footer_text:
        rows.append(
            [para(footer_text, _style("footer", fontSize=8, textColor=GREY, alignment=TA_CENTER))]
        )
    block = Table(rows, colWidths=[CONTENT_WIDTH])
    block.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return block


def _render(view: DocumentView, company: Company | None, footer_text: str | None) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"{view.title} {view.number}",
        author=(company.legal_name or company.name) if company else "",
    )
    story: list[Flowable] = []
    logo = _logo()
    if logo:
        story += [logo, Spacer(1, 3 * mm)]
    story += _header(company, view)
    story += [_reference_boxes(view), Spacer(1, 5 * mm), _items(view), Spacer(1, 6 * mm)]
    story.append(AtPageBottom(_footer_block(view, footer_text)))
    doc.build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()


# ---------------------------------------------------------------------- public API
def render_quotation_pdf(
    quotation: Quotation, company: Company | None, footer: str | None
) -> bytes:
    customer = quotation.customer
    view = DocumentView(
        title="Quotation",
        number=quotation.quote_number,
        doc_date=quotation.quote_date,
        customer_code=customer.code,
        customer_lines=_customer_lines(customer),
        order_no=quotation.customer_reference or "",
        prices_include_tax=quotation.prices_include_tax,
        lines=list(quotation.lines),
        subtotal=quotation.subtotal,
        discount_total=quotation.discount_total,
        tax_total=quotation.tax_total,
        total=quotation.total,
        left_rows=[
            ("Validity:", f"Valid until {date_text(quotation.valid_until)}"),
            ("Received by:", ""),
            ("Payment Terms:", _payment_terms(customer)),
            ("Date:", ""),
            ("Signed:", ""),
        ],
        extra_totals=[],
        notes=quotation.notes,
    )
    return _render(view, company, footer)


def render_invoice_pdf(invoice: SalesInvoice, company: Company | None, footer: str | None) -> bytes:
    customer = invoice.customer
    title = {
        InvoiceStatus.DRAFT: "Draft Invoice",
        InvoiceStatus.CANCELLED: "Cancelled Invoice",
    }.get(invoice.status, "Tax Invoice")
    view = DocumentView(
        title=title,
        number=invoice.invoice_number or "DRAFT",
        doc_date=invoice.invoice_date,
        customer_code=customer.code,
        customer_lines=_customer_lines(customer),
        order_no=invoice.customer_reference or "",
        prices_include_tax=invoice.prices_include_tax,
        lines=list(invoice.lines),
        subtotal=invoice.subtotal,
        discount_total=invoice.discount_total,
        tax_total=invoice.tax_total,
        total=invoice.total,
        left_rows=[
            ("Due Date:", date_text(invoice.due_date)),
            ("Received by:", ""),
            ("Payment Terms:", _payment_terms(customer)),
            ("Date:", ""),
            ("Signed:", ""),
        ],
        extra_totals=[("Amount Paid", invoice.amount_paid), ("Balance Due", invoice.balance_due)],
        notes=invoice.notes,
    )
    return _render(view, company, footer)
