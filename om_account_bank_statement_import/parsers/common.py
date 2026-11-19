"""Helpers shared by the parsers."""

import hashlib


def set_content_import_ids(transactions, reference_key=None):
    """Give an identifier to the transactions of a format that has none of its own (QIF) or whose numbering
    depends on how the file was cut (MT940).

    The identifier is made of what the transaction is (date, amount, reference and a digest of its texts),
    never of its position in the file or of the number of the statement: a file overlapping an earlier one
    gives its transactions the same identifiers, and they are not imported twice. Identical transactions
    of one file are told apart by their occurrence (``-2``, ``-3``...).

    :param list transactions: the transactions of one bank account, in the order of the file
    :param str reference_key: the key of the transaction holding a reference worth putting in clear
    """
    occurrences = {}
    for transaction in transactions:
        texts = '|'.join(str(transaction.get(key) or '') for key in (
            'payment_ref', 'narration', 'partner_name', 'account_number', 'ref', 'transaction_type'))
        digest = hashlib.sha1(texts.encode('utf-8')).hexdigest()[:12]
        parts = [
            transaction['date'].isoformat() if hasattr(transaction['date'], 'isoformat') else str(transaction['date']),
            '%.2f' % transaction['amount'],
            (transaction.get(reference_key) or '') if reference_key else '',
            digest,
        ]
        base = '-'.join(part for part in parts if part)
        occurrences[base] = occurrences.get(base, 0) + 1
        transaction['unique_import_id'] = base if occurrences[base] == 1 else f'{base}-{occurrences[base]}'
