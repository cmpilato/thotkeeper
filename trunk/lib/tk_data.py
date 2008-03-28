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

TK_DATA_VERSION = 2

class _item:
    # Taken from ViewCVS. :-)
    def __init__(self, **kw):
        vars(self).update(kw)

class TKEntry:
    def __init__(self, author='', subject='', text='',
                 year=None, month=None, day=None, id=None, tags=[]):
        self.author = author
        self.subject = subject
        self.text = text
        self.year = year
        self.month = month
        self.day = day
        self.id = id
        self.tags = tags

    def get_author(self):
        return self.author

    def get_subject(self):
        return self.subject

    def get_text(self):
        return self.text

    def get_date(self):
        return self.year, self.month, self.day
    
    def get_id(self):
        return self.id
    
    def get_tags(self):
        return self.tags
    
class TKEntries:
    def __init__(self):
        self.entry_tree = {}
        self.listeners = []

    def register_listener(self, func):
        """Append FUNC to the list of functions called whenever one of
        the diary entries changes.  FUNC is a callback which accepts
        the following: this instance, an event, year, month, and day."""
        self.listeners.append(func)

    def enumerate_entries(self, func):
        """Call FUNC for each diary entry, ordered by time and
        intra-day index.  FUNC is a callback which accepts a TKEntry
        parameter."""
        years = self.get_years()
        years.sort()
        for year in years:
            months = self.get_months(year)
            months.sort()
            for month in months:
                days = self.get_days(year, month)
                days.sort()
                for day in days:
                    ids = self.get_ids(year, month, day)
                    ids.sort()
                    for id in ids:
                        func(self.get_entry(year, month, day, id))
        
    def set_entry(self, year, month, day, author, subject, text, id, tags=[]):
        if not self.entry_tree.has_key(year):
            self.entry_tree[year] = {}
        if not self.entry_tree[year].has_key(month):
            self.entry_tree[year][month] = {}
        if not self.entry_tree[year][month].has_key(day):
            self.entry_tree[year][month][day] = {}
        #FIXME: Create an index to store all the tags to help find entries
        entry = TKEntry(author, subject, text, year, month, day, id, tags)
        self.entry_tree[year][month][day][id] = entry
        for func in self.listeners:
            func(entry, year, month, day, id)

    def remove_entry(self, year, month, day, id):
        del self.entry_tree[year][month][day][id]
        if not len(self.entry_tree[year][month][day].keys()):
            del self.entry_tree[year][month][day]
        if not len(self.entry_tree[year][month].keys()):
            del self.entry_tree[year][month]
        if not len(self.entry_tree[year].keys()):
            del self.entry_tree[year]
        for func in self.listeners:
            func(None, year, month, day, id)

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
    
    def get_ids(self, year, month, day):
        """Return the IDS in YEAR, MONTH, and DAY which have associated
        TKEntry objects."""
        return self.entry_tree[year][month][day].keys()
    
    def get_entry(self, year, month, day, id):
        """Return the TKEntry associated with YEAR, MONTH, and DAY,
        or None if no such entry exists."""
        try:
            return self.entry_tree[year][month][day][id]
        except:
            return None
    
    def get_first_id(self, year, month, day):
        """Return the id of the first entry for that day"""
        try:
            day_keys = self.entry_tree[year][month][day].keys()
            day_keys.sort()
            return day_keys[0]
        except:
            return None
        
    def get_last_id(self, year, month, day):
        """Return the id of the last entry for that day"""
        try:
            day_keys = self.entry_tree[year][month][day].keys()
            day_keys.sort()
            return day_keys[-1]
        except:
            return None
        
    def get_id_pos(self, year, month, day, id):
        """Return the position of that id in the list for that day
         - 0 if no entries for that day
         - len(entries) if the id not found""" 
        try:
            day_keys = self.entry_tree[year][month][day].keys()
            day_keys.sort()
        except:
            return 0
        try:
            return day_keys.index(id)
        except:
            return len(day_keys)
        
    def get_next_id(self, year, month, day, id):
        """Get the id of the next entry for that day
         - or None if no more in the list """
        try:
            day_keys = self.entry_tree[year][month][day].keys()
            day_keys.sort()
            idx = day_keys.index(id)
            return day_keys[idx+1]
        except:
            return None
        
    def get_prev_id(self, year, month, day, id):
        """Get the id of the previous entry for that day
        - or the last entry if the supplied id is not found"""
        try:
            day_keys = self.entry_tree[year][month][day].keys()
            day_keys.sort()
            idx = day_keys.index(id)
            return day_keys[idx-1]
        except:
            return self.get_last_id(year, month, day)

class TKDataVersionException(Exception):
    pass

class TKDataParser(xmllib.XMLParser):
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

    Version 1 (unreleased): Adds an "id" attribute to entries for the
    purposes of distinguishing multiple entries for a given day.

       <diary version="1">
         <entries>
           <entry year="YYYY" month="M" day="D" id="N">
             <author>CDATA</author>
             <subject>CDATA</subject>
             <text>CDATA</text>
           </entry>
           ...
         </entries>
       </diary>
       
    Version 2 (unreleased): Adds an optional <tags> tag to entries. 
    Which contains 1 or more <tag> tags.
       
       <diary version="2">
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
        def _write_entry(entry):
            year, month, day = entry.get_date()
            id = entry.get_id()
            tags = entry.get_tags()
            fp.write('  <entry year="%s" month="%s" day="%s" id="%s">\n'
                     % (year, month, day, id))
            fp.write('   <author>%s</author>\n'
                     % (xml.sax.saxutils.escape(entry.get_author())))
            fp.write('   <subject>%s</subject>\n'
                     % (xml.sax.saxutils.escape(entry.get_subject())))
            if len(tags):
                fp.write('   <tags>\n')
                for tag in tags:
                    fp.write('    <tag>%s</tag>\n'
                             % (xml.sax.saxutils.escape(tag)))
                fp.write('   </tags>\n')
            fp.write('   <text>%s</text>\n'
                     % (xml.sax.saxutils.escape(entry.get_text())))
            fp.write('  </entry>\n')
        entries.enumerate_entries(_write_entry)
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
        if not ('id' in attr_names):
            self.cur_entry['id'] = '1'
    def end_entry(self):
        self.entries.set_entry(int(self.cur_entry['year']),
                               int(self.cur_entry['month']),
                               int(self.cur_entry['day']),
                               self.cur_entry.get('author', ''),
                               self.cur_entry.get('subject', ''),
                               self.cur_entry.get('text', ''),
                               int(self.cur_entry['id']),
                               self.cur_entry.get('tags', []))
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
    def start_tags(self, attrs):
        if not self.cur_entry:
            raise Exception("Invalid XML file.")
        self.cur_entry['tags'] = []
    def start_tag(self, attrs):
        if not self.cur_entry:
            raise Exception("Invalid XML file.")
        self.buffer = ''
    def end_tag(self):
        self.cur_entry['tags'].append(self.buffer)
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
