# ThotKeeper -- a personal daily journal application.
#
# Copyright (c) 2004-2025 C. Michael Pilato.  All rights reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE file which can be found at the top level of the ThotKeeper
# distribution.
#
# Website: https://github.com/cmpilato/thotkeeper

import os
import shutil
import tempfile
import xml.sax
from xml.sax.saxutils import escape as _xml_escape
from .entries import (TKEntries, TKEntry)

TK_DATA_VERSION = 1


class TKDataVersionException(Exception):
    pass


class TKDataParser(xml.sax.handler.ContentHandler):
    """XML Parser class for reading and writing diary data files.

    The diary data files currently use a single XML container tag,
    <diary>, which carries a 'version' attribute to indicate the
    format of the data it contains.  A missing version attribute
    indicates version 0 of the format.  Here are the supported
    versions and their formats:

    Version 0 (ThotKeeper 0.1): The original format.

       <diary [version="0"]>
         <entries>
           <entry year="YYYY" month="M" day="D">
             <author>CDATA</author>
             <subject>CDATA</subject>
             <text>CDATA</text>
           </entry>
           ...
         </entries>
       </diary>

    Version 1 (ThotKeeper 0.2): Adds an "id" attribute to entries for the
    purposes of distinguishing multiple entries for a given day.  Adds
    an optional <tags> tag to entries, which contains 1 or more <tag>
    tags.

       <diary version="1">
         <author global="True/False">CDATA</author>
         <entries>
           <entry year="YYYY" month="M" day="D" id="N">
             <author>CDATA</author>
             <subject>CDATA</subject>
             <tags>
                <tag>CDATA</tag>
                ...
             </tags>
             <text>CDATA</text>
           </entry>
           ...
         </entries>
       </diary>
    """

    TKJ_TAG_AUTHOR  = 'author'
    TKJ_TAG_DIARY   = 'diary'
    TKJ_TAG_ENTRIES = 'entries'
    TKJ_TAG_ENTRY   = 'entry'
    TKJ_TAG_SUBJECT = 'subject'
    TKJ_TAG_TAG     = 'tag'
    TKJ_TAG_TAGS    = 'tags'
    TKJ_TAG_TEXT    = 'text'

    _valid_parents = {
        TKJ_TAG_AUTHOR: [TKJ_TAG_DIARY, TKJ_TAG_ENTRY],
        TKJ_TAG_DIARY: [],
        TKJ_TAG_ENTRIES: [TKJ_TAG_DIARY],
        TKJ_TAG_ENTRY: [TKJ_TAG_ENTRIES],
        TKJ_TAG_SUBJECT: [TKJ_TAG_ENTRY],
        TKJ_TAG_TAG: [TKJ_TAG_TAGS],
        TKJ_TAG_TAGS: [TKJ_TAG_ENTRY],
        TKJ_TAG_TEXT: [TKJ_TAG_ENTRY],
        }

    def __init__(self, entries):
        self.cur_entry = None
        self.buffer = None
        self.entries = entries
        self.tag_stack = []
        self.entries.set_author_global(False)
        # If we are loading a file, we want there to be no global
        # author *unless* one is actually found in the file (but the
        # default should still be True for new files

    def _validate_tag(self, name, parent_tag):
        valid_parents = self._valid_parents[name]
        if parent_tag is None and not valid_parents:
            return
        if parent_tag and valid_parents and parent_tag in valid_parents:
            return
        raise Exception("Unexpected tag (%s) in parent (%s)"
                        % (name, parent_tag and parent_tag or ""))

    def startElement(self, name, attrs):
        # Validate ...
        parent_tag = self.tag_stack and self.tag_stack[-1] or None
        self._validate_tag(name, parent_tag)
        self.tag_stack.append(name)

        # ... and operate.
        if name == self.TKJ_TAG_DIARY:
            try:
                version = int(attrs['version'])
            except Exception:
                version = 0
            if version > TK_DATA_VERSION:
                raise TKDataVersionException("Data version newer than program "
                                             "version; please upgrade.")
        elif name == self.TKJ_TAG_ENTRY:
            attr_names = list(attrs.keys())
            if not (('month' in attr_names) and
                    ('year' in attr_names) and
                    ('day' in attr_names)):
                raise Exception("Invalid XML file.")
            self.cur_entry = dict(attrs)
            if not ('id' in attr_names):
                self.cur_entry['id'] = '1'
        elif name == self.TKJ_TAG_AUTHOR:
            if not self.cur_entry:
                if 'global' not in list(attrs.keys()):
                    raise Exception("Invalid XML file.")
                if attrs['global'].lower() == 'false':
                    self.entries.set_author_global(False)
                else:
                    self.entries.set_author_global(True)
            self.buffer = ''
        elif name == self.TKJ_TAG_TAGS:
            self.cur_entry['tags'] = []
        elif name in [self.TKJ_TAG_SUBJECT,
                      self.TKJ_TAG_TAG,
                      self.TKJ_TAG_TEXT]:
            self.buffer = ''

    def characters(self, ch):
        if self.buffer is not None:
            self.buffer = self.buffer + ch
        return

    def endElement(self, name):
        # Pop from the tag stack ...
        del self.tag_stack[-1]

        # ... and operate.
        if name == self.TKJ_TAG_ENTRY:
            self.entries.store_entry(TKEntry(self.cur_entry.get('author', ''),
                                             self.cur_entry.get('subject', ''),
                                             self.cur_entry.get('text', ''),
                                             int(self.cur_entry['year']),
                                             int(self.cur_entry['month']),
                                             int(self.cur_entry['day']),
                                             int(self.cur_entry['id']),
                                             self.cur_entry.get('tags', [])))
            self.cur_entry = None
        elif name == self.TKJ_TAG_AUTHOR:
            if self.cur_entry:
                self.cur_entry['author'] = self.buffer
            else:
                self.entries.set_author_name(self.buffer)
            self.buffer = None
        elif name in [self.TKJ_TAG_SUBJECT, self.TKJ_TAG_TEXT]:
            self.cur_entry[name] = self.buffer
            self.buffer = None
        elif name == self.TKJ_TAG_TAG:
            self.cur_entry['tags'].append(self.buffer)


def parse_data(datafile):
    """Parse an XML file, returning a TKEntries object."""
    entries = TKEntries()
    if datafile:
        handler = TKDataParser(entries)
        xml.sax.parse(datafile, handler)
    return entries


def unparse_data(datafile, entries):
    """Unparse a TKEntries object into an XML file, using an
    intermediate tempfile to try to reduce the chances of clobbering a
    previously-good datafile with a half-baked one."""
    fdesc, fname = tempfile.mkstemp()
    fp = os.fdopen(fdesc, 'w', encoding='utf-8')
    try:
        fp.write('<?xml version="1.0"?>\n'
                 '<diary version="%d">\n' % (TK_DATA_VERSION))
        if not entries:
            entries = TKEntries()
        if entries.get_author_name() is not None:
            fp.write(' <author global="%s">%s</author>\n'
                     % (entries.get_author_global() and "true" or "false",
                        _xml_escape(entries.get_author_name())))
        fp.write(' <entries>\n')

        def _write_entry(entry):
            year, month, day = entry.get_date()
            id = entry.get_id()
            tags = entry.get_tags()
            fp.write('  <entry year="%s" month="%s" day="%s" id="%s">\n'
                     % (year, month, day, id))
            author = entry.get_author()
            if author:
                fp.write('   <author>%s</author>\n'
                         % (_xml_escape(author)))
            subject = entry.get_subject()
            if subject:
                fp.write('   <subject>%s</subject>\n'
                         % (_xml_escape(subject)))
            if len(tags):
                fp.write('   <tags>\n')
                for tag in tags:
                    fp.write('    <tag>%s</tag>\n'
                             % (_xml_escape(tag)))
                fp.write('   </tags>\n')
            fp.write('   <text>%s</text>\n'
                     % (_xml_escape(entry.get_text())))
            fp.write('  </entry>\n')
        entries.enumerate_entries(_write_entry)
        fp.write(' </entries>\n</diary>\n')
        fp.close()
        # We use shutil.move() instead of os.rename() because the former
        # can deal with moves across volumes while the latter cannot.
        shutil.move(fname, datafile)
    finally:
        if os.path.exists(fname):
            os.unlink(fname)
