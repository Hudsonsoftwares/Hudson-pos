import io
import logging

from odoo import models

_logger = logging.getLogger(__name__)

try:
    import pypdf as PyPDF2
    from pypdf.generic import NameObject, ArrayObject, NumberObject, DictionaryObject, NullObject
except ImportError:
    try:
        import PyPDF2
        from PyPDF2.generic import NameObject, ArrayObject, NumberObject, DictionaryObject, NullObject
    except ImportError:
        PyPDF2 = None
        NameObject = ArrayObject = NumberObject = DictionaryObject = NullObject = None
        _logger.warning("Neither 'pypdf' nor 'PyPDF2' is available. Annual report TOC link enhancements will be disabled.")


class IrActionsReportAnnual(models.Model):
    """Override to ensure internal PDF Table of Contents links work seamlessly
    across Google Chrome (PDFium), Microsoft Edge, and all other PDF viewers.
    """

    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        pdf_content, report_type = super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)
        
        if not PyPDF2 or not NameObject:
            return pdf_content, report_type

        report = self._get_report(report_ref)
        if not report or report.report_name != 'hudson_accounting_enhancements.report_annual':
            return pdf_content, report_type

        # Post-process PDF to convert all TOC links to internal PDF page destinations
        try:
            pdf_content = self._fix_annual_report_toc_links(pdf_content)
        except Exception:
            # Fallback gracefully if PDF parsing encounters an unexpected structure
            pass

        return pdf_content, report_type

    def _fix_annual_report_toc_links(self, pdf_bytes):
        """Rewrites link annotations in the PDF so TOC links jump directly
        to internal PDF pages in Google Chrome and Microsoft Edge.
        """
        if not PyPDF2 or not NameObject:
            return pdf_bytes
        page_mapping = {
            'attestation': 3,
            'balance_sheet': 4,
            'profit_loss': 5,
            'preamble': 6,
            'accounting_principles': 7,
            'intangible_tangible': 8,
            'inventory_valuation': 9,
            'financial_resources': 10,
            'workforce': 11,
            'aged_payable': 12,
            'aged_receivable': 13,
            'asset_information': 14,
            'liabilities_information': 15,
            'income_statement': 16,
            'taxation': 17,
            'supporting_documents': 18,
        }

        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        writer = PyPDF2.PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        total_pages = len(writer.pages)

        # Process all pages for link annotations
        for page in writer.pages:
            if "/Annots" in page:
                for annot in page["/Annots"]:
                    obj = annot.get_object()
                    dest = obj.get("/Dest")
                    action_obj = obj.get("/A")
                    uri = ""
                    if action_obj:
                        uri = str(action_obj.get("/URI") or "")

                    target_page_num = None
                    for anchor, p_num in page_mapping.items():
                        if anchor in uri.lower():
                            target_page_num = p_num
                            break

                    if target_page_num and target_page_num <= total_pages:
                        target_page = writer.pages[target_page_num - 1]
                        dest_array = ArrayObject([
                            target_page.indirect_reference,
                            NameObject("/XYZ"),
                            NumberObject(0),
                            NumberObject(800),
                            NullObject()
                        ])
                        goto_action = DictionaryObject({
                            NameObject("/S"): NameObject("/GoTo"),
                            NameObject("/D"): dest_array,
                        })
                        obj[NameObject("/A")] = goto_action
                        obj[NameObject("/Dest")] = dest_array
                    elif dest:
                        if isinstance(dest, ArrayObject) and len(dest) >= 5 and dest[1] == "/XYZ" and dest[4] == 0:
                            dest[4] = NullObject()
                        goto_action = DictionaryObject({
                            NameObject("/S"): NameObject("/GoTo"),
                            NameObject("/D"): dest,
                        })
                        obj[NameObject("/A")] = goto_action

                    # Ensure no visual border rectangle is rendered around the link
                    obj[NameObject("/Border")] = ArrayObject([NumberObject(0), NumberObject(0), NumberObject(0)])
                    if NameObject("/BS") in obj:
                        del obj[NameObject("/BS")]
                    if NameObject("/C") in obj:
                        del obj[NameObject("/C")]

        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()
