#!/usr/bin/python
# -*- coding: utf-8 -*-

# various util helpers to deal with frus collection
import re
import warnings
import bs4
from bs4 import NavigableString
import bleach
import csv
from unidecode import unidecode
from collections import Counter, OrderedDict
import copy

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

"""
####################################XML Volumes#############################
the following functions are for parsing xml FRUS volumes coming from
https://github.com/HistoryAtState/frus
"""
# class_list = []

def _get_tag_attrs(soup, tag='div'):
    """
    Takes a BeautifulSoup object and returns a list of tag attributes.
    """
    return [t.attrs for t in soup.findAll(tag)]


def _get_name_ids(el_tag, sec_id, name_tag='persName'):
    """
    Takes a bs2 tag object, i.e. doc part, and return all name id
    for persons mentioned in doc.
    """
    if sec_id == 'persons':
        return dict(
            [(n['xml:id'], __clean_name(n.get_text()))
             for n in el_tag.findAll(name_tag)])
    else:
        ids = []
        for t in el_tag.findAll(name_tag):
            try:
                ids.append(t['corresp'])
            except KeyError:
                continue
        return ids


def __clean_name(name_text):
    """
    Removes newline and whitespace chars from name.
    """
    return re.sub('\\n\s*', '', name_text)


def get_doc_sections(text, tag='div'):
    """
    Takes raw (xml) text and returns a list of document sections.
    """
    text = unidecode(text)
    soup = bs4.BeautifulSoup(text, 'xml')
    return soup.findAll(tag)


def parse_xml(raw_text, vol_name, geo_regex_list=None, markup=None,
              check_doc_num=False, geo_only=False):
    """
    Takes raw (xml) text and returns a dict.

    Parameters
    ----------
    raw_text : string
    vol_name : string
        name of the volume to be use to create doc_ids
    geo_regex_list : None or list of strings
        if None no geo tagging is done;
        list of the form iso_numSEPgeo_regex; for example:
        276##\sgermany|\sd\.{,1}e\.{,1}\s|\sd\.{,1}e\.{,1}u\.{,1}\s|berlin
        see geo_helpers.iso_tag() for more details
    markup : list of tuples or None
        if not None, tuple[0] is the xml tag to be marked up; tuple[1] is
        string to mark; ex: ('persName', '###') wil replace tag.string in
        every tag in bodysoup.findAll('persName') with
        '###'+tag.string+'###'
    check_doc_num: bool
        if True will check that the number of document tag in the entire
        soup matches the number of docs produced
    geo_only : bool
        if True will parse only geo data from documents in body
    Returns
    -------
    dict
    """

    soup = bs4.BeautifulSoup(raw_text, 'xml')
    if check_doc_num:
        check_doc_num = len(soup.findAll('div', {'type': 'document'}))
    header = _parse_xml_header(soup)
    text = _parse_xml_text(soup, vol_name, geo_regex_list, markup, check_doc_num, geo_only)


    return {'header': header, 'text': text}


def _parse_xml_header(soup):
    """
    parses the header and returns a dict of header entities
    """
    header = soup.find('teiHeader')
    pub_info = header.find('publicationStmt')
    pub_date = None

    if pub_info:
        pub_date = str(pub_info.find('date').getText())
        pub_place = str(pub_info.find('pubPlace').getText())
    editors = [str(t.getText()) for t in header.findAll('editor')]
    
    title_complete = header.find('title', {'type': 'complete'})
    if title_complete:
        title_complete = __clean_decode(title_complete.getText())
    
    title_series = header.find('title', {'type': 'series'})
    if title_series:
        title_series = __clean_decode(title_series.getText())

    title_subseries = header.find('title', {'type': 'subseries'})
    if title_subseries:
        title_subseries = __clean_decode(title_subseries.getText())

    title_volnum = header.find('title', {'type': 'volumenumber'})
    if title_volnum:
        title_volnum = __clean_decode(title_volnum.getText())

    title_vol = header.find('title', {'type': 'volume'})
    if title_vol:
        title_vol = __clean_decode(title_vol.getText())

    return {'title_complete': title_complete, 'title_series': title_series,
            'title_subseries': title_subseries, 'title_volnum': title_volnum,
            'title_vol': title_vol, 'date': pub_date, 'location': pub_place,
            'editors': editors}


def __clean_decode(string):
    string = re.sub(r'\n\s+', ' ', string)
    return re.sub(r'^[,\.;:\s]*|\s+$', '', string)


def _parse_xml_text(soup, vol_name, geo_regex_list, markup,
                    check_doc_num, geo_only):
    """
    wrapper to parse the main text part of the XML
    """
    preface = _parse_xml_preface(soup)
    sources = _parse_xml_sources(soup)
    terms = _parse_xml_terms(soup)
    persons = _parse_xml_persons(soup)
    body = _parse_xml_body(soup, vol_name, geo_regex_list, markup,
                           check_doc_num, geo_only)
    index = _parse_xml_index(soup, vol_name)
    return {'preface': preface, 'sources': sources, 'terms': terms,
            'persons': persons, 'body': body, 'index': index}


def _parse_xml_preface(soup):
    preface = soup.find('div', {'xml:id': 'preface'})
    if preface is None:
        return {'body': None}
    body = preface.getText().strip()
    return {'body': body}


def _parse_xml_sources(soup):
    sources = soup.find('div', {'xml:id': 'sources'})
    if sources is None:
        return {'body': None}
    body = sources.getText().strip()
    return {'body': body}


def _parse_xml_terms(soup):
    terms = soup.find('div', {'xml:id': 'terms'})
    if terms is None:
        return []
    terms_list = terms.find('list')
    terms_items = terms_list.findAll('item')
    return [__parse_xml_item(t, 'term', 'acronym') for t in terms_items]


def __parse_xml_item(item, tag, type_name):
    regex = re.compile(r'.*')
    t = item.find(tag, {'xml:id': regex})
    if t is None:
        return
    name = __clean_decode(t.getText())
    tei_id = unidecode(t.attrs['xml:id'])
    tei_id = re.sub(r'#', '', tei_id)
    t.extract()
    desc = __clean_decode(item.getText())
    desc = re.sub(r'^\n[, ]*', '', desc)
    return {'tei_id': tei_id, type_name: name, 'description': desc}


def _parse_xml_persons(soup):
    persons = soup.find('div', {'xml:id': 'persons'})
    if persons is None:
        persons = soup.find('div', {'xml:id': 'names'})
    if persons is None:
        return []
    persons_list = persons.find('list')
    persons_items = persons_list.findAll('item')
    return [__parse_xml_item(t, 'persName', 'name') for t in persons_items]


def _parse_xml_index(soup, vol_name):
    index = soup.find('div', {'xml:id': 'index'})
    if index is None:
        return []
    index_list = index.find('list')
    if index_list is None:
        return []
    index_items = index_list.findAll('item')
    return [__parse_xml_index(t, vol_name) for t in index_items]


def __parse_xml_index(item, vol_name):
    refs = item.findAll('ref')
    ref_docs = []
    for r in refs:
        try:
            ref = str(r.attrs['target'])
        except KeyError:
            continue
        ref = vol_name + re.sub(r'^#', '', ref)
        ref_docs.append(ref)
        r.extract()
    body = __clean_decode(item.getText())
    body = re.sub(r'( ,)*$', r'', body)
    body = re.sub(r'[ \n,]*$|^[ \n,]*', r'', body)
    persons = __get_persons(item).values()
    return {'body': body, 'refs': ref_docs, 'persons': persons}


def _parse_xml_body(soup, vol_name, geo_regex_list, markup, check_doc_num,
                    geo_only):
    """
    Parses the main body of the xml document.

    Note: the "compilation" structure is supressed, and_parse_xml_body
    returns a list of chapters, each of which is a list of document dicts.

    Parameters
    ----------
    soup : BeautifulSoup object
    vol_name : string
        user for doc references
    geo_regex_list : None or list of strings
        if None no geo tagging is done;
        list of the form iso_numSEPgeo_regex; for example:
        276##\sgermany|\sd\.{,1}e\.{,1}\s|\sd\.{,1}e\.{,1}u\.{,1}\s|berlin
        see geo_helpers.iso_tag() for more details
    markup : list of tuples or None
        if not None, tuple[0] is the xml tag to be marked up; tuple[1] is
        string to mark; ex: ('persName', '###') wil replace tag.string in
        every tag in bodysoup.findAll('persName') with
        '###'+tag.string+'###'
    check_doc_num: bool or int
        if not False will check that the number of document tag in the entire
        soup matches the number of docs produced
    geo_only : bool
        if True parse on geo data from documents in body

    Returns
    -------
    chapt_list : list of dicts
        each contains 'chapter' and 'title' keys

    """
    body = soup.find('body')
    if markup:
        for t in markup:
            for tag in body.findAll(t[0]):
                if tag.string:
                    tag.string = t[1] + tag.string + t[1]
    chapt_list = []
    chapters = body.findAll('div', {'type': 'chapter'})
    # if there are no chapters just get the docs
    if not chapters:
        title = None
        chapter = _parse_xml_documents(body, vol_name, geo_regex_list, geo_only)
        chapt_list.append({'title': title, 'chapter': chapter})
    for chapt in chapters:
        # check if there are any nested chapters
        nest_chapts = chapt.findAll('div', {'type': 'chapter'})
        for c in nest_chapts:
            c.extract()
        title = chapt.find('head').getText()
        title = unidecode(title)
        chapter = _parse_xml_documents(chapt, vol_name, geo_regex_list, geo_only)
        chapt_list.append({'title': title, 'chapter': chapter})
        # once chapter is done extract for the file doc sweep
        chapt.extract()
    # one final doc sweep to make sure badly nested docs are grabbed
    title = None
    chapter = _parse_xml_documents(body, vol_name, geo_regex_list, geo_only)
    if chapter:
        chapt_list.append({'title': title, 'chapter': chapter})
    # check for doc number missmatch
    if check_doc_num:
        num_docs = sum([len(c['chapter']) for c in chapt_list])
        if check_doc_num != num_docs:
            warnings.warn("Document number mismatch for volume %s" % vol_name)
    return chapt_list



def extract_classification(doc_id, doc):
    classifications = OrderedDict([(r'PERSONAL AND CONFIDENTIAL', 'Confidential'),
                               (r'PERSONALANDCONFIDENTIAL',   'Confidential'),
                               (r'TOP SECRETPRIORITY',        'Top Secret'),
                               (r'TOPSECRETPRIORITY',         'Top Secret'),
                               (r'TOP SECRETNIACT',           'Top Secret'),
                               (r'TOPSECRETNIACT',            'Top Secret'),
                               (r'TOP SECRET',    'Top Secret'),
                               (r'TOPSECRET',    'Top Secret'),
                               (r'SECRETPRIORITY',            'Secret'),
                               (r'CONFIDENTIAL',              'Confidential'),
                               (r'SECRET',                    'Secret') 
                              ]
                             )

    classification = None
    
    # First the source column
    if doc['source']:
        for class_pattern in classifications.keys():
            if class_pattern == "Secret":
                class_pattern += '([^a-zA-Z]|\s)+'
            match = re.search(class_pattern, doc['source'], flags=re.DOTALL|re.IGNORECASE)
            if match:
                classification = match.group()
                classification = re.sub(r'\W', r'', classification.strip())
                break
    
    # Second, check if the body has [Source: blah blah Secret; blah]
    if classification == None and doc['raw_body']:
        bracket_match = re.search(r'\[Source.*?\]', doc['raw_body'], flags=re.DOTALL|re.IGNORECASE)
        if bracket_match:
            bracket_match = bracket_match.group()
            for class_pattern in classifications.keys():
                if class_pattern == "Secret":
                    class_pattern += r'([^a-zA-Z]|\s)+'
                match = re.search(class_pattern, bracket_match,flags=re.DOTALL|re.IGNORECASE)
                if match:
                    classification = match.group()
                    classification = re.sub(r'\W', r'', classification.strip())
                    break
    
    # Third, pattern like the following in body text:  '\n\nTop SecretNIACT\n\n'
    if classification == None and doc['raw_body']:
        for class_pattern in classifications.keys():
            pattern = '\n\n' + class_pattern + '\n\n'
            match = re.search(pattern, doc['raw_body'],flags=re.IGNORECASE)
            if match:
                classification = match.group()
                classification = re.sub(r'\W', r'', classification.strip())
                break

    # Fourth: check title
    if classification == None and doc['title']:
        for class_pattern in classifications.keys():
            class_pattern += r'([^a-zA-Z]|\s)+'
            match = re.search(class_pattern, doc['title'],flags=re.DOTALL|re.IGNORECASE)
            if match:
                classification = match.group()
                classification = re.sub(r'\W', r'', classification.strip())
                break
                    
    if classification is not None:
        classification = re.sub(r'[^a-zA-Z]', r'', classification)
        classification = classifications[classification.upper()]

    return classification



def _parse_xml_documents(soup, vol_name, geo_regex_list, geo_only):
    """
    Parses documents contained in each chapter.

    Parameters
    ----------
    soup : BeautifulSoup object
    vol_name : string
        user for doc references
    geo_regex_list : None or list of strings
        if None no geo tagging is done;
        list of the form iso_numSEPgeo_regex; for example:
        276##\sgermany|\sd\.{,1}e\.{,1}\s|\sd\.{,1}e\.{,1}u\.{,1}\s|berlin
        see geo_helpers.iso_tag() for more details
    geo_only : bool
        if True parse on geo data from documents in body

    Returns
    -------
    doc_list : list of dicts
        each contains 'doc_num' and 'doc_info' keys

    """
    doc_list = []
    documents = soup.findAll('div', {'type': 'document'})
    for doc in documents:
        # check if there are any nested documents
        nest_docs = doc.findAll('div', {'type': 'document'})
        for d in nest_docs:
            d.extract()
        doc_dict = {}
        doc_id, doc_num = _get_doc_identifiers(doc, vol_name)
        if doc_id is None:
            print("Error: Could not generate valid doc_id!")
            continue
        if geo_only:
            # main text
            body_text = doc.getText()
            doc_dict = {}
            # geo-iso data
            if geo_regex_list:
                doc_dict['country_iso'] = Counter(iso_tag(body_text,
                                                          geo_regex_list))
            doc_list.append({'id': doc_id, 'doc_num': doc_num, 'doc_info':
                             doc_dict})
            # extract the doc for the final sweep
            doc.extract()
        body_text = doc.getText()

        # HEAD
        head = doc.find('head')
        if head is None:
            source_tag = doc.find('note', {'type': 'source'})
            try:
                doc_dict['source'] = __clean_decode(source_tag.getText())
            except AttributeError:
                doc_dict['source'] = None
            doc_dict['title'] = None
            doc_dict['from'] = {}
            doc_dict['to'] = {}

            footnotes = doc.find_all('note')
            fnarray = []
            fncount = 1
            if footnotes:
                for fn in footnotes:
                    if not fn.find(attrs={"rend": "inline"}):
                        fnsoup = bs4.BeautifulSoup('<sup></sup>', 'xml')
                        tag = fnsoup.sup
                        tag.append(str(fncount))
                        fncount += 1
                        fntext = __clean_decode(fn.getText())
                        fnarray.append(fntext)
                        fn.replace_with(tag)
        else:
            source_tag = head.find('note', {'type': 'source'})
            try:
                doc_dict['source'] = __clean_decode(source_tag.getText())
            except AttributeError:
                doc_dict['source'] = None
            from_tag = head.find('persName', {'type': 'from'})
            to_tag = head.find('persName', {'type': 'to'})

            footnotes = doc.find_all('note')
            fnarray = []
            fncount = 1
            if footnotes:
                for fn in footnotes:
                    if not fn.find(attrs={"rend": "inline"}):
                        fnsoup = bs4.BeautifulSoup('<sup></sup>', 'xml')
                        tag = fnsoup.sup
                        tag.append(str(fncount))
                        fncount += 1
                        fntext = __clean_decode(fn.getText())
                        fnarray.append(fntext)
                        fn.replace_with(tag)




            doc_dict['title'] = bleach.clean(str(head), tags=['sup'], strip=True)
            doc_dict['title_docview'] = re.sub(r'(<sup>)(\d+)(</sup>)', r'<a href="#%s_n\2"><sup>\2</sup></a>' % doc_id, doc_dict['title'])
            doc_dict['title'] = re.sub(r'<sup.*?</sup>', r'', doc_dict['title'])
            head.extract()
            try:
                from_name = __clean_decode(from_tag.getText())
                from_id = from_tag.attrs.get('corresp', None)
            except AttributeError:
                from_name = None
                from_id = None
            doc_dict['from'] = {from_id: from_name}
            try:
                to_name = __clean_decode(to_tag.getText())
                to_id = to_tag.attrs.get('corresp', None)
            except AttributeError:
                to_name = None
                to_id = None
            doc_dict['to'] = {to_id: to_name}
        # DATE/PLACE
        dateline_tag = doc.find('dateline')
        try:
            place_name = dateline_tag.find('placeName').getText()
        except AttributeError:
            place_name = None
        doc_dict['location'] = place_name
        try:
            date_str = dateline_tag.find('date').attrs.get('when', None)
            dateline_tag.extract()
        except AttributeError:
            date_str = None
        doc_dict['date'] = date_str
        # SUBJECT
        subject_tag = doc.find('list', {'type': 'subject'})
        try:
            subject = __clean_decode(subject_tag.getText())
            subject = re.sub(r'\n|SUBJECT', '', subject)
        except AttributeError:
            subject = None
        doc_dict['subject'] = subject
        try:
            subject_terms = __get_term_refs(subject_tag)
            subject_tag.extract()
        except AttributeError:
            subject_terms = None
        doc_dict['subject_terms'] = subject_terms
        # persNames
        doc_dict['persons'] = __get_persons(doc)

        body_text = __clean_decode(str(doc.contents))
        body_text = re.sub(r'(<sup>)(\d+)(</sup>)', r'<a href="#%s_n\2"><sup>\2</sup></a>' % doc_id, body_text)
        
        body_text = bleach.clean(body_text, tags=['a','sup','p','ul','ol','li','item', 'list', 'label', 'closer', 'note'], strip=True)
        body_text = re.sub('<label>(.*?)</label>.*?<item>(.*?)</item>', r'<li value="\1"> \2</li>', body_text, flags=re.DOTALL)
        body_text = re.sub(r'<list>', r'<ol>', body_text)
        body_text = re.sub(r'</list>', r'</ol>', body_text)
        body_text = re.sub('<closer>(.*?)</closer>', r'<p>\1</p>', body_text, flags=re.DOTALL)
        body_text = re.sub('<note(.*?)/note>', r'<p\1/p>', body_text, flags=re.DOTALL)

        if len(fnarray) > 0: 
            body_text += '<hr><ol class="footnote"> '
            for i, fn in enumerate(fnarray,1):
                body_text +=  '<li id="%s_n'%doc_id + str(i) + '" value="' + str(i) +'">' + fn + ' </li>\n'
            body_text += ' </ol>'

        body_text = '<div collection="frus">' + body_text + '</div>'
        doc_dict['body'] = body_text

        raw_body = copy.deepcopy(body_text)
        raw_body = re.sub('<sup>.*?</sup>', '', raw_body, flags=re.DOTALL)
        raw_body = re.sub('<ol class="footnote">.*?</ol>', '', raw_body, flags=re.DOTALL)
        raw_body = bs4.BeautifulSoup('<raw_body>' + raw_body + '</raw_body>', 'xml')

        if raw_body:
            raw_body = raw_body.getText()
        else:
            raw_body = u''
        doc_dict['raw_body'] = raw_body.strip()

        if doc_dict['source'] == None:
            source_match = re.search(r'\[Source.*?\]', body_text,flags=re.DOTALL)
            if source_match:
                doc_dict['source'] = source_match.group().strip('[]')

        if not doc_dict['title']:
            doc_dict['title_docview'] = None

        doc_dict['classification'] = extract_classification(doc_id, doc_dict)
        # term references
        try:
            doc_dict['term_refs'] = __get_term_refs(doc)
        except UnicodeEncodeError:
            # try to encode the doc
            doc_str = str(doc).decode('ascii', 'ignore')
            doc = bs4.BeautifulSoup(doc_str, 'xml')
            doc_dict['term_refs'] = __get_term_refs(doc)
        # doc references
        doc_refs = __get_doc_refs(doc, vol_name)
        doc_dict['doc_refs'] = doc_refs
        doc_list.append({'id': doc_id, 'doc_num': doc_num, 'doc_info':
                         doc_dict})
        # geo-iso data
        if geo_regex_list:
            doc_dict['country_iso'] = Counter(iso_tag(body_text,
                                                      geo_regex_list))
        # extract the doc for the final sweep
        doc.extract()

    return doc_list


def _get_doc_identifiers(doc, vol_name):
    """
    Extract doc_num and doc_id from document.
    """
    try:
        doc_num = doc.attrs['n']
    except KeyError:
        # This num is sometimes found different places in some of the volumes.
        doc_num = None
        for soup in doc.findAll():
            try:
                doc_num = soup.attrs['n']
                break
            except:
                continue
            doc_num = doc.find('note').attrs['n']

    try:
        doc_id = vol_name + doc.attrs['xml:id']
    except KeyError:
        # This id is sometimes found different places in some of the volumes.
        doc_id = None
        for soup in doc.findAll():
            try:
                xml_id = soup.attrs['xml:id']
                doc_id = vol_name + xml_id
                break
            except:
                continue
    if doc_id is None:
        if doc_num is not None:
            doc_id = vol_name + 'd' + doc_num

    return doc_id, doc_num


def __get_term_refs(soup):
    term_regex = re.compile(r'#t_.*$')
    return Counter([re.sub(r'#', '', t.attrs['target']) for t in
                    soup.findAll('gloss', {'target': term_regex})])


def __get_doc_refs(doc, vol_name):
    doc_regex = re.compile(r'.*d\d{1,4}$')
    return Counter([__parse_doc_ref(t.attrs['target'], vol_name) for t in
                    doc.findAll('ref', {'target': doc_regex})])


def __parse_doc_ref(ref, vol_name):
    ref = re.sub(r'#', '', ref)
    if 'frus' not in ref:
        ref = vol_name+ref
    return ref


def __get_persons(doc):
    """
    Takes a BeautifulSoup object and finds all mentioned persons.
    """
    persons_dict = {}
    for p in doc.findAll('persName'):
        try:
            tei_id = p.attrs['corresp'] #unidecode(p.attrs['corresp'])
            tei_id = re.sub(r'[#\^\.]', '', tei_id)
        except (KeyError, AttributeError):
            continue
        if tei_id in persons_dict:
            persons_dict[tei_id]['count'] += 1
        else:
            persons_dict[tei_id] = {}
            persons_dict[tei_id]['name'] = p.getText()
            persons_dict[tei_id]['count'] = 1
    return persons_dict

if __name__ == "__main__":
    # for experimention
    import os

    # set up some paths
    DATA = os.getenv("DATA")
    FRUS = os.path.join(DATA, 'declass', 'frus')
    RAW = os.path.join(FRUS, 'raw')
    PROCESSED = os.path.join(FRUS, 'processed')
    XML = os.path.join(RAW, 'frus', 'volumes')

    # get the iso regex list
    declass_home = os.getenv("DECLASSENG_HOME")
    config_dir = os.path.join(declass_home, 'processing', 'common', 'config')
    regex_file = os.path.join(config_dir, 'country_regex.txt')
    with open(regex_file) as f:
        iso_regex_list = list(f)
    iso_regex_list = [item.strip() for item in iso_regex_list]

    xml_vol = open(os.path.join(XML, 'frus1952-54v03.xml')).read()
    vol_name = 'TEST'
    xml_dict = parse_xml(xml_vol, vol_name, iso_regex_list)
