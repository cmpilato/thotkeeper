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

import os
import shutil
import tempfile
import xml.sax

TK_DATA_VERSION = 1

# sorted() is new to Python 2.4, but an implementation of it that works for
# our list-sorting needs is easy enough to patch in for older versions.
try:
    mysorted = sorted
    del(mysorted)
except NameError:
    def sorted(list):
        if list is None:
            return None
        newlist = list[:]
        newlist.sort()
        return newlist

# sets (and the set() function) are new to Python 2.4, but an
# implementation of it that works for our list-sorting needs is easy
# enough to patch in for older versions.
try:
    myset = set()
    del(myset)
except NameError:
    class MySet:
        def __init__(self):
            self.items = {}
        def add(self, thing):
            self.items[thing] = None
        def remove(self, thing):
            del self.items[thing]
        def __iter__(self):
            return self.items.keys().__iter__()
    def set():
        return MySet()


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
        self.tag_tree = {}
        self.listeners = []
        self.tag_listeners = []
        self.author_name = None
        self.author_global = True

    def register_listener(self, func):
        """Append FUNC to the list of functions called whenever one of
        the diary entries changes.  FUNC is a callback which accepts
        the following: this instance, an event, year, month, and day."""
        self.listeners.append(func)
        
    def register_tag_listener(self, func):
        self.tag_listeners.append(func)

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
        
    def enumerate_tag_entries(self, func):
        tags = sorted(self.get_tags())
        for tag in tags:
            entries = sorted(self.get_entries_by_tag(tag))
            for entry in entries:
                func(entry, tag)
    
    def _update_tags(self, oldtags, newtags, entry):
        """Update the tag set association for ENTRY.  OLDTAGS are the
        tags is used to carry; NEWTAGS are the tags it now carries.
        Notify the tag listeners of relevant changes.  If this change
        removes the last association of an entry with a given tag,
        prune the tag."""
        addtags = filter(lambda x: x not in oldtags, newtags)
        removetags = filter(lambda x: x not in newtags, oldtags)
        for tag in newtags:
            for func in self.tag_listeners:
                func(tag, entry, True)
        for tag in addtags:
            if not self.tag_tree.has_key(tag):
                self.tag_tree[tag] = set()
            self.tag_tree[tag].add((entry.year, entry.month,
                                    entry.day, entry.id))
        for tag in removetags:
            if not self.tag_tree.has_key(tag):
                continue
            entry_key = (entry.year, entry.month, entry.day, entry.id)
            if entry_key in self.tag_tree[tag]:
                self.tag_tree[tag].remove(entry_key)
                for func in self.tag_listeners:
                    func(tag, entry, False)
                if not self.tag_tree[tag]: 
                    del self.tag_tree[tag]
        
    def store_entry(self, entry):
        year, month, day = entry.get_date()
        if not self.entry_tree.has_key(year):
            self.entry_tree[year] = {}
        if not self.entry_tree[year].has_key(month):
            self.entry_tree[year][month] = {}
        if not self.entry_tree[year][month].has_key(day):
            self.entry_tree[year][month][day] = {}
        id = entry.get_id()
        oldtags = []
        if self.entry_tree[year][month][day].has_key(id):
            oldtags = sorted(self.entry_tree[year][month][day][id].tags)
        self.entry_tree[year][month][day][id] = entry
        newtags = sorted(entry.tags)
        self._update_tags(oldtags, newtags, entry)
        for func in self.listeners:
            func(entry, year, month, day, id)
                    
    def remove_entry(self, year, month, day, id):
        entry = self.entry_tree[year][month][day][id]
        oldtags = entry.tags
        self._update_tags(oldtags, [], entry)
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
    
    def get_tags(self):
        return self.tag_tree.keys()
    
    def get_entries_by_tag(self, tag):
        entry_keys = self.tag_tree[tag]
        return map(lambda x: self.entry_tree[x[0]][x[1]][x[2]][x[3]],
                   entry_keys)
    
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
        """Return 1-based position of ID in the ordered list of
        entries for YEAR, MONTH, DAY.  If ID is not found, return the
        position in that list it would hold if appended to the list (1
        if the list is empty; number_of_entries + 1 otherwise)."""
        try:
            day_keys = self.entry_tree[year][month][day].keys()
            day_keys.sort()
        except:
            day_keys = []
        try:
            return day_keys.index(id) + 1
        except:
            return len(day_keys) + 1
        
    def get_next_id(self, year, month, day, id):
        """Return the id of the entry (in the set of entries for YEAR,
        MONTH, DAY) which follows the entry for ID, or None if no
        entries follow the one for ID."""
        try:
            day_keys = self.entry_tree[year][month][day].keys()
            day_keys.sort()
            idx = day_keys.index(id)
            return day_keys[idx+1]
        except:
            return None
        
    def get_prev_id(self, year, month, day, id):
        """Return the id of the entry (in the set of entries for YEAR,
        MONTH, DAY) which precedes the entry for ID, or the last entry
        for that day if no entry for ID can be found."""
        try:
            day_keys = self.entry_tree[year][month][day].keys()
            day_keys.sort()
            idx = day_keys.index(id)
            return day_keys[idx-1]
        except:
            return self.get_last_id(year, month, day)

    def get_author_name(self):
        return self.author_name
    
    def get_author_global(self):
        return self.author_global
    
    def set_author_name(self, name):
        self.author_name = name
        
    def set_author_global(self, enable):
        self.author_global = enable

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

    Version 1 (unreleased): Adds an "id" attribute to entries for the
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
        TKJ_TAG_AUTHOR  : [ TKJ_TAG_DIARY, TKJ_TAG_ENTRY ],
        TKJ_TAG_DIARY   : [  ],
        TKJ_TAG_ENTRIES : [ TKJ_TAG_DIARY ],
        TKJ_TAG_ENTRY   : [ TKJ_TAG_ENTRIES ],
        TKJ_TAG_SUBJECT : [ TKJ_TAG_ENTRY ],
        TKJ_TAG_TAG     : [ TKJ_TAG_TAGS ],
        TKJ_TAG_TAGS    : [ TKJ_TAG_ENTRY ],
        TKJ_TAG_TEXT    : [ TKJ_TAG_ENTRY ],
        }
    
    def __init__(self, entries):
        self.cur_entry = None
        self.buffer = None
        self.entries = entries
        self.tag_stack = []
        self.entries.set_author_global(False)
        # If we are loading a file, we want there to be no global author *unless*
        # one is actually found in the file (but the default should still be
        # True for new files

    def _validate_tag(self, name, parent_tag):
        valid_parents = self._valid_parents[name]
        if parent_tag is None and not valid_parents:
            return
        if parent_tag and valid_parents and parent_tag in valid_parents:
            return
        raise Exception("Unexpected tag (%s) in parent (%s)" \
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
            except:
                version = 0
            if version > TK_DATA_VERSION:
                raise TKDataVersionException("Data version newer than program "
                                             "version; please upgrade.")
        elif name == self.TKJ_TAG_ENTRY:
            attr_names = attrs.keys()
            if not (('month' in attr_names) \
                    and ('year' in attr_names) \
                    and ('day' in attr_names)):
                raise Exception("Invalid XML file.")
            self.cur_entry = dict(attrs)
            if not ('id' in attr_names):
                self.cur_entry['id'] = '1'
        elif name == self.TKJ_TAG_AUTHOR:
            if not self.cur_entry:
                if (not 'global' in attrs.keys()):
                    raise Exception("Invalid XML file.")
                if (attrs['global'].lower() == 'false'):
                    self.entries.set_author_global(False)
                else:
                    self.entries.set_author_global(True)
            self.buffer = ''
        elif name == self.TKJ_TAG_TAGS:
            self.cur_entry['tags'] = []
        elif name == self.TKJ_TAG_SUBJECT \
             or name == self.TKJ_TAG_TAG \
             or name == self.TKJ_TAG_TEXT:
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
        elif name == self.TKJ_TAG_SUBJECT \
             or name == self.TKJ_TAG_TEXT:
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
    fp = os.fdopen(fdesc, 'w')
    try:
        fp.write('<?xml version="1.0"?>\n'
                 '<diary version="%d">\n' % (TK_DATA_VERSION))
        if not entries:
            entries = TKEntries()
        if (entries.get_author_name() != None):
            fp.write(' <author global="%s">%s</author>\n' 
                     % (entries.get_author_global() and "true" or "false",
                        entries.get_author_name().encode('utf8')))
        fp.write(' <entries>\n')
        def _write_entry(entry):
            year, month, day = entry.get_date()
            id = entry.get_id()
            tags = entry.get_tags()
            fp.write('  <entry year="%s" month="%s" day="%s" id="%s">\n'
                     % (year, month, day, id))
            author = xml.sax.saxutils.escape(entry.get_author())
            if author:
                fp.write('   <author>%s</author>\n'
                         % (author.encode('utf8')))
            subject = xml.sax.saxutils.escape(entry.get_subject())
            if subject:
                fp.write('   <subject>%s</subject>\n'
                         % (subject.encode('utf8')))
            if len(tags):
                fp.write('   <tags>\n')
                for tag in tags:
                    fp.write('    <tag>%s</tag>\n'
                             % (xml.sax.saxutils.escape(tag.encode('utf8'))))
                fp.write('   </tags>\n')
            fp.write('   <text>%s</text>\n'
                     % (xml.sax.saxutils.escape(entry.get_text().encode('utf8'))))
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
