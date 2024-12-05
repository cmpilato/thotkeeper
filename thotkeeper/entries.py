# ThotKeeper -- a personal daily journal application.
#
# Copyright (c) 2004-2024 C. Michael Pilato.  All rights reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE file which can be found at the top level of the ThotKeeper
# distribution.
#
# Website: http://www.thotkeeper.org/

from functools import reduce


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

    def __eq__(self, other):
        return ([self.year, self.month, self.day, self.id] ==
                [other.year, other.month, other.day, other.id])

    def __lt__(self, other):
        return ([self.year, self.month, self.day, self.id] <
                [other.year, other.month, other.day, other.id])


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
        addtags = [x for x in newtags if x not in oldtags]
        removetags = [x for x in oldtags if x not in newtags]
        for tag in newtags:
            for func in self.tag_listeners:
                func(tag, entry, True)
        for tag in addtags:
            if tag not in self.tag_tree:
                self.tag_tree[tag] = set()
            self.tag_tree[tag].add((entry.year, entry.month,
                                    entry.day, entry.id))
        for tag in removetags:
            if tag not in self.tag_tree:
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
        if year not in self.entry_tree:
            self.entry_tree[year] = {}
        if month not in self.entry_tree[year]:
            self.entry_tree[year][month] = {}
        if day not in self.entry_tree[year][month]:
            self.entry_tree[year][month][day] = {}
        id = entry.get_id()
        oldtags = []
        if id in self.entry_tree[year][month][day]:
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
        if not len(list(self.entry_tree[year][month][day].keys())):
            del self.entry_tree[year][month][day]
        if not len(list(self.entry_tree[year][month].keys())):
            del self.entry_tree[year][month]
        if not len(list(self.entry_tree[year].keys())):
            del self.entry_tree[year]
        for func in self.listeners:
            func(None, year, month, day, id)

    def get_years(self):
        """Return the years which have days with associated TKEntry
        objects."""
        return list(self.entry_tree.keys())

    def get_months(self, year):
        """Return the months in YEAR which have days with associated
        TKEntry objects."""
        return list(self.entry_tree[year].keys())

    def get_days(self, year, month):
        """Return the days in YEAR and MONTH which have associated
        TKEntry objects."""
        return list(self.entry_tree[year][month].keys())

    def get_ids(self, year, month, day):
        """Return the IDS in YEAR, MONTH, and DAY which have associated
        TKEntry objects."""
        return list(self.entry_tree[year][month][day].keys())

    def get_tags(self):
        return list(self.tag_tree.keys())

    def get_entries_by_tag(self, tag):
        entry_keys = self.tag_tree[tag]
        return [self.entry_tree[x[0]][x[1]][x[2]][x[3]] for x in entry_keys]

    def get_entries_by_partial_tag(self, tagstart):
        """Return all the entries that start with tagstart"""
        tagstartsep = tagstart + '/'
        taglist = [x for x in list(self.tag_tree.keys())
                   if ((x == tagstart) or (x.startswith(tagstartsep)))]
        entrylist = list(map(self.get_entries_by_tag, taglist))
        return reduce(lambda x, y: x + y, entrylist)

    def get_entry(self, year, month, day, id):
        """Return the TKEntry associated with YEAR, MONTH, and DAY,
        or None if no such entry exists."""
        try:
            return self.entry_tree[year][month][day][id]
        except Exception:
            return None

    def get_first_id(self, year, month, day):
        """Return the id of the first entry for that day"""
        try:
            day_keys = list(self.entry_tree[year][month][day].keys())
            day_keys.sort()
            return day_keys[0]
        except Exception:
            return None

    def get_last_id(self, year, month, day):
        """Return the id of the last entry for that day"""
        try:
            day_keys = list(self.entry_tree[year][month][day].keys())
            day_keys.sort()
            return day_keys[-1]
        except Exception:
            return None

    def get_new_id(self, year, month, day):
        """Return the first unused id for a given day."""
        id = self.get_last_id(year, month, day)
        if id is None:
            return None
        else:
            return id + 1

    def get_id_pos(self, year, month, day, id):
        """Return 1-based position of ID in the ordered list of
        entries for YEAR, MONTH, DAY.  If ID is not found, return the
        position in that list it would hold if appended to the list (1
        if the list is empty; number_of_entries + 1 otherwise)."""
        try:
            day_keys = list(self.entry_tree[year][month][day].keys())
            day_keys.sort()
        except Exception:
            day_keys = []
        try:
            return day_keys.index(id) + 1
        except Exception:
            return len(day_keys) + 1

    def get_next_id(self, year, month, day, id):
        """Return the id of the entry (in the set of entries for YEAR,
        MONTH, DAY) which follows the entry for ID, or None if no
        entries follow the one for ID."""
        try:
            day_keys = list(self.entry_tree[year][month][day].keys())
            day_keys.sort()
            idx = day_keys.index(id)
            return day_keys[idx + 1]
        except Exception:
            return None

    def get_prev_id(self, year, month, day, id):
        """Return the id of the entry (in the set of entries for YEAR,
        MONTH, DAY) which precedes the entry for ID, or the last entry
        for that day if no entry for ID can be found."""
        try:
            day_keys = list(self.entry_tree[year][month][day].keys())
            day_keys.sort()
            idx = day_keys.index(id)
            return day_keys[idx - 1]
        except Exception:
            return self.get_last_id(year, month, day)

    def get_author_name(self):
        return self.author_name

    def get_author_global(self):
        return self.author_global

    def set_author_name(self, name):
        self.author_name = name

    def set_author_global(self, enable):
        self.author_global = enable
