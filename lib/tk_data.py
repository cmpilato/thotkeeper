#!/usr/bin/python
#
# ThotKeeper -- a personal daily journal application.
#
# Copyright (c) 2004-2008 C. Michael Pilato.  All rights reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE file which can be found at the top level of the ThotKeeper
# distribution.
#
# Website: http://www.thotkeeper.org/

import warnings
warnings.filterwarnings('ignore', '.*', DeprecationWarning)
warnings.filterwarnings('ignore', category=DeprecationWarning)

### TODO: Convert to xml.sax
import xmllib
import xml.sax.saxutils

TK_DATA_VERSION = 0

class _item:
    # Taken from ViewCVS. :-)
    def __init__(self, **kw):
        vars(self).update(kw)

class TKEntry:
    def __init__(self, author='', subject='', text='',
                 year=None, month=None, day=None):
        self.author = author
        self.subject = subject
        self.text = text
        self.year = year
        self.month = month
        self.day = day

    def get_author(self):
        return self.author

    def get_subject(self):
        return self.subject

    def get_text(self):
        return self.text

    def get_date(self):
        return self.year, self.month, self.day
    
    
class TKEntries:
    def __init__(self):
        self.entry_tree = {}
        self.listeners = []

    def register_listener(self, func):
        """Append FUNC to the list of functions called whenever one of
        the diary entries changes.  FUNC is a callback which accepts
        the following: this instance, an event, year, month, and day."""
        self.listeners.append(func)
        
    def set_entry(self, year, month, day, author, subject, text):
        if not self.entry_tree.has_key(year):
            self.entry_tree[year] = {}
        if not self.entry_tree[year].has_key(month):
            self.entry_tree[year][month] = {}
        entry = TKEntry(author, subject, text, year, month, day)
        self.entry_tree[year][month][day] = entry
        for func in self.listeners:
            func(entry, year, month, day)

    def remove_entry(self, year, month, day):
        del self.entry_tree[year][month][day]
        if not len(self.entry_tree[year][month].keys()):
            del self.entry_tree[year][month]
        if not len(self.entry_tree[year].keys()):
            del self.entry_tree[year]
        for func in self.listeners:
            func(None, year, month, day)

    def get_years(self):
        """Return the years which have days with associated TKEntry
        objects."""
        return self.entry_tree.keys()

    def get_months(self, year):
        """Return the months in YEAR which have days with associated
        TKEntry objects."""
        return self.entry_tree[year].keys()
        
    def get_days(self, year, month):
        """Return the days in YEAR and MONTH which have associated
        TKEntry objects."""
        return self.entry_tree[year][month].keys()
    
    def get_entry(self, year, month, day):
        """Return the TKEntry associated with YEAR, MONTH, and DAY,
        or None if no such entry exists."""
        try:
            return self.entry_tree[year][month][day]
        except:
            return None

class TKDataVersionException(Exception):
    pass

class TKDataParser(xmllib.XMLParser):
    """XML Parser class for reading and writing diary data files."""

    def parse_data(self, datafile):
        """Parse an XML file."""
        self.cur_entry = None
        self.buffer = None
        self.entries = TKEntries()
        if datafile:
            self.feed(open(datafile).read())
        return self.entries
    
    def unparse_data(self, datafile, entries):
        """Unparse data into an XML file."""
        fp = open(datafile, 'w')
        fp.write('<?xml version="1.0"?>\n'
                 '<diary version="%d">\n'
                 ' <entries>\n' % (TK_DATA_VERSION))
        if not entries:
            entries = TKEntries()
        years = entries.get_years()
        years.sort()
        for year in years:
            months = entries.get_months(year)
            months.sort()
            for month in months:
                days = entries.get_days(year, month)
                days.sort()
                for day in days:
                    entry = entries.get_entry(year, month, day)
                    text = xml.sax.saxutils.escape(entry.get_text())
                    author = xml.sax.saxutils.escape(entry.get_author())
                    subject = xml.sax.saxutils.escape(entry.get_subject())
                    fp.write('  <entry year="%s" month="%s" day="%s">\n' \
                             % (year, month, day))
                    fp.write('   <author>%s</author>\n' % (author))
                    fp.write('   <subject>%s</subject>\n' % (subject))
                    fp.write('   <text>%s</text>\n' % (text))
                    fp.write('  </entry>\n')
        fp.write(' </entries>\n</diary>\n')
        
    ### XMLParser callback functions
        
    def start_diary(self, attrs):
        try:
            version = int(attrs['version'])
        except:
            version = 0
        if version > TK_DATA_VERSION:
            raise TKDataVersionException("Data version is newer than program "
                                         "version; please upgrade.")
    def start_entry(self, attrs):
        if self.cur_entry is not None:
            raise Exception("Invalid XML file.")
        attr_names = attrs.keys()
        if not (('month' in attr_names) \
                and ('year' in attr_names) \
                and ('day' in attr_names)):
            raise Exception("Invalid XML file.")
        self.cur_entry = attrs
    def end_entry(self):
        self.entries.set_entry(int(self.cur_entry['year']),
                               int(self.cur_entry['month']),
                               int(self.cur_entry['day']),
                               self.cur_entry.get('author', ''),
                               self.cur_entry.get('subject', ''),
                               self.cur_entry.get('text', ''))
        self.cur_entry = None
    def start_author(self, attrs):
        if not self.cur_entry:
            raise Exception("Invalid XML file.")
        self.buffer = ''
    def end_author(self):
        self.cur_entry['author'] = self.buffer
        self.buffer = None
    def start_subject(self, attrs):
        if not self.cur_entry:
            raise Exception("Invalid XML file.")
        self.buffer = ''
    def end_subject(self):
        self.cur_entry['subject'] = self.buffer
        self.buffer = None
    def start_text(self, attrs):
        if not self.cur_entry:
            raise Exception("Invalid XML file.")
        self.buffer = ''
    def end_text(self):
        self.cur_entry['text'] = self.buffer
        self.buffer = None
    def handle_data(self, data):
        if self.buffer is not None:
            self.buffer = self.buffer + data
