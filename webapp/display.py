"""Presentation only; preserve original metadata for audit records."""
import re
from datetime import datetime


def package_number(group):
    # Ignore upload indexes and date-prefixed aggregate archive names.
    docs=([group['letter']] if group.get('letter') else [])+group['documents']
    for doc in docs:
        for part in doc.get('scope', ())[1:]:
            match=re.match(r'^\s*(\d{1,3}(?:-\d{1,3})?)(?:[._)\s]|-(?!\d)|$)',part,re.I)
            if match:
                return '-'.join(str(int(number)) for number in match.group(1).split('-'))
    return ''


def law_label(law,member,number):
    # Keep representative metadata for bill grouping/audit, not the display label.
    return (f'{number}. ' if number else '')+law


def unit_labels(units,number):
    """Number separate summary units within a package, regardless of law name."""
    labels=[]
    for branch,unit in enumerate(units,1):
        display_number=number
        if number and len(units)>1:
            display_number=f'{number}-{branch}'
        labels.append(law_label(unit['law'],unit.get('representative',''),display_number))
    return labels


def organization_label(agency,department):
    return '\n'.join(str(value).strip() for value in (agency,department) if value and str(value).strip())


def department_label(record):
    """Use the article's organizational unit, with the chapter as fallback."""
    name=record['department_name']
    parent=record.get('article_title','').strip()
    parent=re.sub(r'에 두는 (?:과|부서)$','',parent)
    # Article headings sometimes name the head rather than the organization.
    parent=re.sub(r'(실|국|본부|원|소|센터|단|부)장$',r'\1',parent)
    if parent in {'센터','지방과학수사연구소 등'} or not re.search(r'(실|국|본부|원|소|센터|단|부|관|대변인)$',parent):
        parent=''
    if not parent or parent==name:
        parent=record.get('organization','').strip()
    return organization_label(parent if parent!=name else '',name)


def deadline_label(value):
    if not value:
        return ''
    try:
        parsed=datetime.fromisoformat(value)
    except ValueError:
        raise ValueError('제출기한 형식 확인 필요') from None
    return f'{parsed.year}.{parsed.month}.{parsed.day}({"월화수목금토일"[parsed.weekday()]})'
