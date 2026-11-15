"""Cryptographic (PKCS#7) signature of a PDF with a .pfx / .p12 certificate.

The document is rewritten once with PyPDF2, then a signature field is added as an
incremental update whose ``/Contents`` holds a detached CMS signature of every byte
of the file except that signature itself (``/ByteRange``), as PDF readers expect.
"""
import io
from datetime import datetime, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7
from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.generic import ArrayObject, DictionaryObject, IndirectObject, NameObject, NumberObject

# Room reserved for the DER signature (certificate chain included)
SIGNATURE_SIZE = 32768
BYTE_RANGE_WIDTH = 60


def _pdf_text(value):
    """PDF text string, UTF-16BE hex encoded so any character is safe."""
    return b'<FEFF' + (value or '').encode('utf-16-be').hex().upper().encode() + b'>'


def _serialize(obj):
    stream = io.BytesIO()
    obj.write_to_stream(stream, None)
    return stream.getvalue()


def certify_pdf(pdf_bytes, pem_key, pem_certificate, extra_pem_certificates=(), name='', reason='', location=''):
    """Return ``pdf_bytes`` signed with the given private key and certificate (PEM bytes)."""
    private_key = serialization.load_pem_private_key(pem_key, password=None)
    certificate = x509.load_pem_x509_certificate(pem_certificate)
    extra_certificates = [x509.load_pem_x509_certificate(pem) for pem in extra_pem_certificates]

    # 1. Plain copy of the document: one classic cross-reference table to append to
    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(pdf_bytes), strict=False).pages:
        writer.add_page(page)
    buffer = io.BytesIO()
    writer.write(buffer)
    base = buffer.getvalue()

    reader = PdfReader(io.BytesIO(base))
    trailer = reader.trailer
    root_ref = trailer.raw_get('/Root')
    root = root_ref.get_object()
    page_ref = root['/Pages']['/Kids'][0]
    page = page_ref.get_object()
    size = int(trailer['/Size'])
    previous_xref = int(base[base.rindex(b'startxref') + len(b'startxref'):].split()[0])

    sig_num, widget_num = size, size + 1
    out = bytearray(base)
    if not out.endswith(b'\n'):
        out += b'\n'
    offsets = {}

    def add_object(num, gen, body):
        offsets[num] = (len(out), gen)
        out.extend(b'%d %d obj\n' % (num, gen) + body + b'\nendobj\n')

    # 2. Signature dictionary, with placeholders for the byte range and the signature
    signing_time = datetime.now(timezone.utc).strftime("D:%Y%m%d%H%M%S+00'00'")
    add_object(sig_num, 0, b''.join([
        b'<< /Type /Sig /Filter /Adobe.PPKLite /SubFilter /adbe.pkcs7.detached\n',
        b'/ByteRange ' + b' ' * BYTE_RANGE_WIDTH + b'\n',
        b'/Contents <' + b'0' * (SIGNATURE_SIZE * 2) + b'>\n',
        b'/M (' + signing_time.encode() + b')',
        b' /Name ' + _pdf_text(name) if name else b'',
        b' /Reason ' + _pdf_text(reason) if reason else b'',
        b' /Location ' + _pdf_text(location) if location else b'',
        b' >>',
    ]))
    # 3. Invisible signature field on the first page
    add_object(widget_num, 0, (
        b'<< /Type /Annot /Subtype /Widget /FT /Sig /Rect [0 0 0 0] /F 132 '
        b'/T ' + _pdf_text('Signature') +
        b' /V %d 0 R /P %d %d R >>' % (sig_num, page_ref.idnum, page_ref.generation)
    ))
    widget_ref = IndirectObject(widget_num, 0, reader)

    new_page = DictionaryObject(page)
    annots = page.get('/Annots')
    annots = list(annots.get_object()) if annots is not None else []
    new_page[NameObject('/Annots')] = ArrayObject(annots + [widget_ref])
    add_object(page_ref.idnum, page_ref.generation, _serialize(new_page))

    new_root = DictionaryObject(root)
    new_root[NameObject('/AcroForm')] = DictionaryObject({
        NameObject('/Fields'): ArrayObject([widget_ref]),
        NameObject('/SigFlags'): NumberObject(3),
    })
    add_object(root_ref.idnum, root_ref.generation, _serialize(new_root))

    # 4. Cross-reference section of the update
    xref_offset = len(out)
    out.extend(b'xref\n')
    for num in sorted(offsets):
        offset, gen = offsets[num]
        out.extend(b'%d 1\n%010d %05d n \n' % (num, offset, gen))
    new_trailer = b'<< /Size %d /Root %d %d R /Prev %d' % (
        max(size, widget_num + 1), root_ref.idnum, root_ref.generation, previous_xref)
    if '/Info' in trailer:
        info = trailer.raw_get('/Info')
        new_trailer += b' /Info %d %d R' % (info.idnum, info.generation)
    if '/ID' in trailer:
        new_trailer += b' /ID ' + _serialize(trailer['/ID'])
    out.extend(b'trailer\n' + new_trailer + b' >>\nstartxref\n%d\n%%%%EOF\n' % xref_offset)

    # 5. Byte range: the whole file but the hexadecimal signature
    sig_start = offsets[sig_num][0]
    contents_start = out.index(b'/Contents <', sig_start) + len(b'/Contents ')
    contents_end = out.index(b'>', contents_start) + 1
    byte_range = b'[0 %d %d %d]' % (contents_start, contents_end, len(out) - contents_end)
    range_start = out.index(b'/ByteRange ', sig_start) + len(b'/ByteRange ')
    out[range_start:range_start + BYTE_RANGE_WIDTH] = byte_range.ljust(BYTE_RANGE_WIDTH)

    signed_data = bytes(out[:contents_start]) + bytes(out[contents_end:])
    builder = pkcs7.PKCS7SignatureBuilder().set_data(signed_data).add_signer(
        certificate, private_key, hashes.SHA256())
    for extra in extra_certificates:
        builder = builder.add_certificate(extra)
    signature = builder.sign(
        serialization.Encoding.DER, [pkcs7.PKCS7Options.DetachedSignature, pkcs7.PKCS7Options.Binary])
    signature_hex = signature.hex().upper().encode()
    if len(signature_hex) > SIGNATURE_SIZE * 2:
        raise ValueError("The certificate chain is too large to sign the document.")
    out[contents_start + 1:contents_end - 1] = signature_hex.ljust(SIGNATURE_SIZE * 2, b'0')
    return bytes(out)
