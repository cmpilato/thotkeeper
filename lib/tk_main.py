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

import sys
import os
import os.path
import time
import string
import tk_data
import wx
import wx.calendar
import wx.xrc
from wx.html import HtmlEasyPrinting

__version__ = "0.4-dev"

month_names = ['January', 'February', 'March', 'April', 
               'May', 'June', 'July', 'August', 
               'September', 'October', 'November', 'December']
month_abbrs = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
               'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


########################################################################
###
###  UPDATE ROUTINES
###

def CheckForUpdates():
    import httplib
    import socket
    import re

    def _version_parse(version):
        match = re.search(r'^([0-9]+)\.([0-9]+)(\.([0-9]+))?', version)
        if match:
            major = int(match.group(1))
            minor = int(match.group(2))
            try:
                patch = int(match.group(4))
            except:
                patch = -1
            return [major, minor, patch]
        raise Exception, "Invalid version string '%s'" % (version)
        
    update_host = "thotkeeper.googlecode.com"
    update_path = "/svn/latest-version.txt"
    http = httplib.HTTPConnection(update_host)
    http.request("GET", update_path)
    response = http.getresponse()
    if response.status == 200:
        contents = response.read().split('\n')
        new_version = _version_parse(contents[0])
        http.close()
        this_version = _version_parse(__version__)
        if new_version > this_version:
            return '.'.join(map(lambda x: str(x), new_version)), contents[1]
        return None, None
    http.close()
    raise Exception, "Unknown error checking for updates (status = %d)" \
          % (errcode)


########################################################################
###
###  CONFIGURATION
###

class TKOptions:

    """A class for managing ThotKeeper configuration options.  The
    current collection of options accessible to consumers is:

       font_face:  font face to use for entry display (string)
       font_size:  size (in points) of the entry font (int)
       data_file:  path of the journal file to use (string)
       position:   location of the top-left window corner (wx.Point)
       size:       size of the window (wx.Size)
       
    """
    CONF_GROUP = 'options'
    CONF_FONT_NAME = CONF_GROUP + '/font-face'
    CONF_FONT_SIZE = CONF_GROUP + '/font-size'
    CONF_DATA_FILE = CONF_GROUP + '/data-file'
    CONF_POSITION = CONF_GROUP + '/window-position'
    CONF_SIZE = CONF_GROUP + '/window-size'
    
    def __init__(self):
        """Initialize the object, and set default values for
        configuration options."""
        self._SetDefaults()

    def _SetDefaults(self):
        """Set the configuration variables to their default values."""
        self.font_face = 'Comic Sans MS'
        self.font_size = 12
        self.data_file = None
        self.position = None
        self.size = wx.Size(600, 400)

    def Read(self):
        """(Re-)read the stored configuration, applying settings atop
        the default collection of values."""
        self._SetDefaults()
        conf = wx.Config(style = wx.CONFIG_USE_LOCAL_FILE)
        self.font_face = conf.Read(self.CONF_FONT_NAME, self.font_face)
        self.font_size = conf.ReadInt(self.CONF_FONT_SIZE, self.font_size)
        if conf.Exists(self.CONF_DATA_FILE):
            self.data_file = conf.Read(self.CONF_DATA_FILE)
        if conf.Exists(self.CONF_POSITION):
            position = conf.Read(self.CONF_POSITION).split(',')
            self.position = wx.Point(int(position[0]), int(position[1]))
        if conf.Exists(self.CONF_SIZE):
            size = conf.Read(self.CONF_SIZE).split(',')
            self.size = wx.Size(int(size[0]), int(size[1]))
        
    def Write(self):
        """Store configuration values using whatever persistant
        storage mechanism the system provides."""
        conf = wx.ConfigBase_Get()
        if self.data_file:
            conf.Write(self.CONF_DATA_FILE, self.data_file)
        conf.Write(self.CONF_FONT_NAME, self.font_face)
        conf.WriteInt(self.CONF_FONT_SIZE, self.font_size)
        if self.position:
            conf.Write(self.CONF_POSITION,
                       "%d,%d" % (self.position.x, self.position.y))
        if self.size:
            conf.Write(self.CONF_SIZE,
                     "%d,%d" % (self.size.GetWidth(), self.size.GetHeight()))
        conf.Flush()

########################################################################
###    
###  ENTRY KEY CLASS
###

class TKEntryKey:
    def __init__(self, year, month, day, id, tag=None):
        self.year = year
        self.month = month
        self.day = day
        self.id = id
        self.tag = tag

    def _compare_tags(self, other):
        ### Because tags look like paths, we use basically the same
        ### algorithm as Subversion's svn_path_compare_paths().
        
        self_tag = self.tag or ''
        other_tag = other.tag or ''

        # Easy case:  the tags are the same
        if self_tag == other_tag:
            return 0
        
        self_tag_len = len(self_tag)
        other_tag_len = len(other_tag)
        min_len = min(self_tag_len, other_tag_len)
        i = 0

        # Skip past common prefix
        while (i < min_len) and (self_tag[i] == other_tag[i]):
            i = i + 1

        # Children are greater than their parents, but less than
        # greater siblings of their parents
        char1 = '\0'
        char2 = '\0'
        if (i < self_tag_len):
            char1 = self_tag[i]
        if (i < other_tag_len):
            char2 = other_tag[i]

        if (char1 == '/') and (i == other_tag_len):
            return 1
        if (char2 == '/') and (i == self_tag_len):
            return -1
        if (i < self_tag_len) and (char1 == '/'):
            return -1
        if (i < other_tag_len) and (char2 == '/'):
            return 1

        # Common prefix was skipped above, next character is compared
        # to determine order
        return cmp(char1, char2)
        
    def __cmp__(self, other):
        tag_cmp = self._compare_tags(other)
        if self.year is not None and other.year is None:
            return -1
        if self.year is None and other.year is not None:
            return 1
        if tag_cmp == 0:
            return cmp([self.year, self.month, self.day, self.id],
                       [other.year, other.month, other.day, other.id])
        return -tag_cmp


########################################################################
###    
###  GENERIC TREE SUBCLASS
###

class TKTreeCtrl(wx.TreeCtrl):
    def __init__(self, parent, style):
        wx.TreeCtrl.__init__(self, parent=parent, style=style)

    def GetRootId(self):
        return self.root_id

    def OnCompareItems(self, item1, item2):
        data1 = self.GetItemData(item1).GetData()
        data2 = self.GetItemData(item2).GetData()
        if data1 is None or data2 is None:
            return 0
        return cmp(data2, data1)  # reverse ordering
        
    def Walker(self, callback, id=None):
        if not id:
            id = self.GetRootItem()
        callback(id)
        cookie = None
        while 1:
            if cookie:
                child_id, cookie = self.GetNextChild(id, cookie)
            else:
                child_id, cookie = self.GetFirstChild(id)
            if not child_id.IsOk():
                break
            self.Walker(callback, child_id)
    
    def FindChild(self, item_id, data):
        cookie = None
        while 1:
            if cookie:
                child_id, cookie = self.GetNextChild(item_id, cookie)
            else:
                child_id, cookie = self.GetFirstChild(item_id)
            if not child_id.IsOk():
                break
            child_data = self.GetItemData(child_id).GetData()
            if child_data == data:
                return child_id
        return None
    
    def Prune(self, item_id):
        while 1:
            parent_id = self.GetItemParent(item_id)
            # Don't delete the root node.
            if not parent_id.IsOk():
                break        
            self.Delete(item_id)
            if self.GetChildrenCount(parent_id):
                break
            item_id = parent_id

    def PruneAll(self):
        self.DeleteChildren(self.root_id)

    def CollapseTree(self):
        try:
            self.CollapseAllChildren(self.root_id)
        except AttributeError:
            self.Collapse(self.root_id)
        self.Expand(self.root_id)


########################################################################
###    
###  EVENT TREE (ORDERED BY DATES AND IDS)
###
        
class TKEventTree(TKTreeCtrl):
    def __init__(self, parent, style):
        TKTreeCtrl.__init__(self, parent, style)
        root_data = wx.TreeItemData(TKEntryKey(None, None, None, None))
        self.root_id = self.AddRoot('ThotKeeper Entries', -1, -1, root_data)

    def GetDateStack(self, year, month, day, id):
        stack = []
        root_id = self.GetRootItem()
        stack.append(root_id) # 0
        item_id = self.FindChild(root_id,
                                 TKEntryKey(year, None, None, None))
        stack.append(item_id) # 1
        if item_id:
            item_id = self.FindChild(item_id,
                                     TKEntryKey(year, month, None, None))
            stack.append(item_id) # 2
            if item_id:
                item_id = self.FindChild(item_id,
                                         TKEntryKey(year, month, day, id))
                stack.append(item_id) # 3
            else:
                stack.append(None) # 3
        else:
            stack.append(None) # 2
            stack.append(None) # 3
        return stack

    def _ItemLabel(self, day, subject):
        return "%02d%s" % (int(day), subject and " - " + subject or '')
    
    def EntryChangedListener(self, entry, year, month, day, id, expand=True):
        """Callback for TKEntries.store_entry()."""
        wx.BeginBusyCursor()
        try:
            stack = self.GetDateStack(year, month, day, id)
            if not entry:
                if stack[3]:
                    self.Prune(stack[3])
            else:
                subject = entry.get_subject()
                if not stack[1]:
                    data = wx.TreeItemData(TKEntryKey(year, None, None, None))
                    stack[1] = self.AppendItem(stack[0],
                                               str(year),
                                               -1, -1, data)
                    self.SortChildren(stack[0])
                if not stack[2]:
                    data = wx.TreeItemData(TKEntryKey(year, month, None, None))
                    stack[2] = self.AppendItem(stack[1],
                                               month_names[month - 1],
                                               -1, -1, data)
                    self.SortChildren(stack[1])
                if not stack[3]:
                    data = wx.TreeItemData(TKEntryKey(year, month, day, id))
                    stack[3] = self.AppendItem(stack[2],
                                               self._ItemLabel(day, subject),
                                               -1, -1, data)
                    self.SortChildren(stack[2])
                else:
                    self.SetItemText(stack[3], self._ItemLabel(day, subject))
                if expand:
                    self.Expand(stack[0])
                    self.Expand(stack[1])
                    self.Expand(stack[2])
                    self.Expand(stack[3])
                self.SelectItem(stack[3])
        finally:
            wx.EndBusyCursor()


########################################################################
###
###  EVENT TREE (ORDERED BY TAGS)
###

class TKEventTagTree(TKTreeCtrl):
    def __init__(self, parent, style):
        TKTreeCtrl.__init__(self, parent, style)
        root_data = wx.TreeItemData(TKEntryKey(None, None, None, None))
        self.root_id = self.AddRoot('ThotKeeper Tags', -1, -1, root_data)

    def GetTagStack(self, tag, year, month, day, id):
        """Return a list of tree item id's, the path of such from the
        root of the tree to the requested item.  If any segment of the
        expected path is missing, the list will be truncated to only
        those segments which exist."""

        tag_path = map(unicode, tag.split('/'))
        stack = []
        prev_id = root_id = self.GetRootItem()
        stack.append(root_id) # 0
        tag = None
        for i in range(len(tag_path)):
            if i == 0:
                tag = tag_path[i]
            else:
                tag = tag + '/' + tag_path[i]
            item_id = self.FindChild(prev_id,
                                     TKEntryKey(None, None, None, None, tag))
            if item_id is None:
                return stack
            stack.append(item_id) # 1, 2, ...
            prev_id = item_id
        item_id = self.FindChild(prev_id,
                                 TKEntryKey(year, month, day, id, tag))
        if item_id:
            stack.append(item_id) # -1
        return stack

    def _ItemLabel(self, day, month, year, subject):
        return "%02d %s %4d%s" \
               % (int(day), month_abbrs[int(month) - 1], int(year),
                  subject and " - " + subject or '')
        
    def EntryChangedListener(self, tag, entry, add=True):
        """Callback for TKEntries.store_entry()."""
        year, month, day = entry.get_date()
        id = entry.get_id()
        wx.BeginBusyCursor()
        try:
            stack = self.GetTagStack(tag, year, month, day, id)
            tag_path = map(unicode, tag.split('/'))
            expected_stack_len = len(tag_path) + 2  # root + tag pieces + entry
            if add == False:
                if len(stack) == expected_stack_len:
                    self.Prune(stack[-1])
            else:
                newtag = None
                for i in range(len(tag_path)):
                    if i == 0:
                        newtag = tag_path[i]
                    else:
                        newtag = newtag + '/' + tag_path[i]
                    if len(stack) == i + 1:
                        data = wx.TreeItemData(TKEntryKey(None, None,
                                                         None, None,
                                                         newtag))
                        stack.append(self.AppendItem(stack[i], tag_path[i],
                                                     -1, -1, data))
                        self.SortChildren(stack[i])
                subject = entry.get_subject()
                if len(stack) == i + 2:
                    data = wx.TreeItemData(TKEntryKey(year, month, day,
                                                     id, newtag))
                    stack.append(self.AppendItem(stack[i + 1],
                                                 self._ItemLabel(day, month,
                                                                 year,
                                                                 subject),
                                                 -1, -1, data))
                    self.SortChildren(stack[i + 1])
                else:
                    self.SetItemText(stack[i + 2],
                                     self._ItemLabel(day, month, year,
                                                     subject))
        finally:
            wx.EndBusyCursor()


########################################################################
###
###  EVENT CALENDAR SUBCLASS
###

class TKEventCal(wx.calendar.CalendarCtrl):
    def SetDayAttr(self, day, has_event):
        if has_event:
            attr = wx.calendar.CalendarDateAttr()
            attr.SetTextColour(wx.RED)
            self.SetAttr(day, attr)
        else:
            self.ResetAttr(day)
        
    def HighlightEvents(self, entries):
        date = self.GetDate()
        year = date.GetYear()
        month = date.GetMonth() + 1
        has_events = 0
        days = []
        years = entries.get_years()
        if year in years:
            months = entries.get_months(year)
            if month in months:
                has_events = 1
                days = entries.get_days(year, month)
        wx.BeginBusyCursor()
        try:
            for day in range(1, 32):
                if day in days and has_events:
                    self.SetDayAttr(day, True)
                else:
                    self.SetDayAttr(day, False)
            self.Refresh(True)
        finally:
            wx.EndBusyCursor()
        
    def EntryChangedListener(self, entry, year, month, day, id):
        """Callback for TKEntries.store_entry()."""
        date = self.GetDate()
        if date.GetYear() != year:
            return
        if (date.GetMonth() + 1) != month:
            return
        wx.BeginBusyCursor()
        try:
            if entry:
                self.SetDayAttr(day, True)
            else:
                self.SetDayAttr(day, False)
        finally:
            wx.EndBusyCursor()


########################################################################
###
###  HTMLEASYPRINTER SUBCLASS
###

class TKEntryPrinter(HtmlEasyPrinting):
    def __init__(self):
        HtmlEasyPrinting.__init__(self)

    def Print(self, filename, title, author, date, text):
        self.PrintText(self._HTMLize(title, author, date, text), filename)

    def PreviewText(self, filename, title, author, date, text):
        HtmlEasyPrinting.PreviewText(self, self._HTMLize(title, author,
                                                         date, text))

    def _HTMLize(self, title, author, date, text):
        return """<html>
<body>
<h2>%s</h2>
<p><i>by <b>%s</b>, on <b>%s</b></i></p>
%s
</body>
</html>
""" % (title or "(no title)",
       author or "(no author)",
       date or "(no date)",
       ''.join(map(lambda x: '<p align="justify">' + x + '</p>\n',
                   text.split('\n'))))

    
########################################################################
###
###  MAIN APPLICATION SUBCLASS
###

class ThotKeeper(wx.App):
    def __init__(self, datafile=None):
        self.cmd_datafile = datafile
        self.datafile = None
        wx.App.__init__(self)

    def OnInit(self):
        """wxWidgets calls this method to initialize the application"""

        # Who am I?
        self.SetVendorName("Red-Bean Software")
        self.SetAppName("ThotKeeper")

        # Get our persisted options into an easily addressable object.
        self.conf = TKOptions()
        self.conf.Read()

        # Get the XML Resource class
        resource_path = os.path.join(os.path.dirname(sys.argv[0]),
                                     'lib', 'tk_resources.xrc')
        self.resources = wx.xrc.XmlResource(resource_path)
        self.calendar_id = self.resources.GetXRCID('TKCalendar')
        self.panel_id = self.resources.GetXRCID('TKPanel')
        self.datetree_id = self.resources.GetXRCID('TKDateTree')
        self.tagtree_id = self.resources.GetXRCID('TKTagTree')
        self.today_id = self.resources.GetXRCID('TKToday')
        self.next_id = self.resources.GetXRCID('TKNext')
        self.prev_id = self.resources.GetXRCID('TKPrev')
        self.date_id = self.resources.GetXRCID('TKEntryDate')
        self.author_id = self.resources.GetXRCID('TKEntryAuthor')
        self.author_label_id = self.resources.GetXRCID('TKEntryAuthorLabel')
        self.subject_id = self.resources.GetXRCID('TKEntrySubject')
        self.tags_id = self.resources.GetXRCID('TKEntryTags')
        self.text_id = self.resources.GetXRCID('TKEntryText')
        self.file_new_id = self.resources.GetXRCID('TKMenuFileNew')
        self.file_open_id = self.resources.GetXRCID('TKMenuFileOpen')
        self.file_save_id = self.resources.GetXRCID('TKMenuFileSave')
        self.file_saveas_id = self.resources.GetXRCID('TKMenuFileSaveAs')
        self.file_revert_id = self.resources.GetXRCID('TKMenuFileRevert')
        self.file_preview_id = self.resources.GetXRCID('TKMenuFilePreview')
        self.file_print_id = self.resources.GetXRCID('TKMenuFilePrint')
        self.file_options_id = self.resources.GetXRCID('TKMenuFileOptions')
        self.file_diary_options_id = self.resources.GetXRCID('TKMenuFileDiaryOptions')
        self.file_quit_id = self.resources.GetXRCID('TKMenuFileQuit')
        self.help_update_id = self.resources.GetXRCID('TKMenuHelpUpdate')
        self.help_about_id = self.resources.GetXRCID('TKMenuHelpAbout')
        self.open_tool_id = self.resources.GetXRCID('TKToolOpen')
        self.choose_font_id = self.resources.GetXRCID('TKChooseFontButton')
        self.font_id = self.resources.GetXRCID('TKFontName')
        self.author_global_id = self.resources.GetXRCID('TKAuthorGlobal')
        self.author_name_id = self.resources.GetXRCID('TKAuthorName')
        self.author_per_entry_id = self.resources.GetXRCID('TKAuthorPerEntry')
        self.tree_edit_id = self.resources.GetXRCID('TKTreeMenuEdit')
        self.tree_dup_id = self.resources.GetXRCID('TKTreeMenuDuplicate')
        self.tree_delete_id = self.resources.GetXRCID('TKTreeMenuDelete')
        self.tree_expand_id = self.resources.GetXRCID('TKTreeMenuExpand')
        self.tree_collapse_id = self.resources.GetXRCID('TKTreeMenuCollapse')
        self.rename_tag_id = self.resources.GetXRCID('TKTagName')

        # Construct our datafile parser and placeholder for data.
        self.entries = None

        # Setup a printer object.
        self.printer = TKEntryPrinter()
        
        # Note that our input file is not modified.
        self.entry_modified = False
        self.ignore_text_event = False
        self.diary_modified = False
        
        # Fetch our main frame.
        self.frame = self.resources.LoadFrame(None, 'TKFrame')

        # Fetch our main panel.
        self.panel = self.frame.FindWindowById(self.panel_id)
        self.panel.Show(False)

        # fetch our options dialog.
        self.options_dialog = self.resources.LoadDialog(self.frame,
                                                        'TKOptions')

        # fetch the per-diary options dialog
        self.diary_options_dialog = self.resources.LoadDialog(self.frame,
                                                              'TKDiaryOptions')
                                                        
        # fetch the rename tag dialog
        self.rename_tag_dialog = self.resources.LoadDialog(self.frame,
                                                        'TKTagRename')

        # Fetch (and assign) our menu bar.
        self.menubar = self.resources.LoadMenuBar('TKMenuBar')
        self.frame.SetMenuBar(self.menubar)

        # Create a status bar.import locale
        self.statusbar = self.frame.CreateStatusBar(2)
        self.statusbar.SetStatusWidths([-1, 100])
        
        # Replace "unknown" XRC placeholders with custom widgets.
        self.cal = TKEventCal(parent=self.panel,
                              style=wx.calendar.CAL_SEQUENTIAL_MONTH_SELECTION)
        self.resources.AttachUnknownControl('TKCalendar',
                                            self.cal, self.panel)
        tree = TKEventTree(parent=self.panel,
                           style=wx.TR_HAS_BUTTONS)
        self.resources.AttachUnknownControl('TKDateTree',
                                            tree, self.panel)
        
        tagtree = TKEventTagTree(parent=self.panel,
                            style = wx.TR_HAS_BUTTONS)
        self.resources.AttachUnknownControl('TKTagTree',
                                            tagtree, self.panel)

        # Populate the tree widget.
        self.tree = self.frame.FindWindowById(self.datetree_id)
        self.tree_root = self.tree.GetRootId()
        self.tag_tree = self.frame.FindWindowById(self.tagtree_id)
        self.tag_tree_root = self.tag_tree.GetRootId()
        
        # Set the default font size for the diary entry text widget.
        self._SetFont(wx.Font(self.conf.font_size, wx.DEFAULT,
                              wx.NORMAL, wx.NORMAL, False,
                              self.conf.font_face))
        
        # Event handlers.  They are the key to the world.
        wx.EVT_CLOSE(self.frame, self._FrameClosure)
        wx.EVT_BUTTON(self, self.today_id, self._TodayButtonActivated)
        wx.EVT_BUTTON(self, self.next_id, self._NextButtonActivated)
        wx.EVT_BUTTON(self, self.prev_id, self._PrevButtonActivated)
        wx.EVT_TEXT(self, self.text_id, self._EntryDataChanged)
        wx.EVT_TEXT(self, self.author_id, self._EntryDataChanged)
        wx.EVT_TEXT(self, self.tags_id, self._EntryDataChanged)
        wx.EVT_TEXT(self, self.subject_id, self._EntryDataChanged)
        wx.calendar.EVT_CALENDAR(self, self.calendar_id, self._CalendarChanged)
        wx.calendar.EVT_CALENDAR_YEAR(self, self.calendar_id, self._CalendarDisplayChanged)
        wx.calendar.EVT_CALENDAR_MONTH(self, self.calendar_id, self._CalendarDisplayChanged)
        wx.EVT_MENU(self, self.file_new_id, self._FileNewMenu)
        wx.EVT_MENU(self, self.file_open_id, self._FileOpenMenu)
        wx.EVT_MENU(self, self.file_save_id, self._FileSaveMenu)
        wx.EVT_MENU(self, self.file_saveas_id, self._FileSaveAsMenu)
        wx.EVT_MENU(self, self.file_revert_id, self._FileRevertMenu)
        wx.EVT_MENU(self, self.file_preview_id, self._FilePreviewMenu)
        wx.EVT_MENU(self, self.file_print_id, self._FilePrintMenu)
        wx.EVT_MENU(self, self.file_diary_options_id, self._FileDiaryOptionsMenu)
        wx.EVT_MENU(self, self.file_options_id, self._FileOptionsMenu)
        wx.EVT_MENU(self, self.file_quit_id, self._FileQuitMenu)
        wx.EVT_MENU(self, self.help_update_id, self._HelpUpdateMenu)
        wx.EVT_MENU(self, self.help_about_id, self._HelpAboutMenu)

        # Event handlers for the Tree widget.
        wx.EVT_TREE_ITEM_ACTIVATED(self, self.datetree_id, self._TreeActivated)
        wx.EVT_RIGHT_DOWN(self.tree, self._TreePopup)
        wx.EVT_MENU(self.tree, self.tree_edit_id, self._TreeEditMenu)
        wx.EVT_MENU(self.tree, self.tree_dup_id, self._TreeDuplicateMenu)
        wx.EVT_MENU(self.tree, self.tree_delete_id, self._TreeDeleteMenu)
        wx.EVT_MENU(self.tree, self.tree_expand_id, self._TreeExpandMenu)
        wx.EVT_MENU(self.tree, self.tree_collapse_id, self._TreeCollapseMenu)
        
        wx.EVT_TREE_ITEM_ACTIVATED(self, self.tagtree_id, self._TreeActivated)
        wx.EVT_RIGHT_DOWN(self.tag_tree, self._TreePopup)
        wx.EVT_MENU(self.tag_tree, self.tree_edit_id, self._TreeEditMenu)
        wx.EVT_MENU(self.tag_tree, self.tree_dup_id, self._TreeDuplicateMenu)
        wx.EVT_MENU(self.tag_tree, self.tree_delete_id, self._TreeDeleteMenu)
        wx.EVT_MENU(self.tag_tree, self.tree_expand_id, self._TreeExpandMenu)
        wx.EVT_MENU(self.tag_tree, self.tree_collapse_id, self._TreeCollapseMenu)

        # Size and position our frame.
        self.frame.SetSize(self.conf.size)
        if self.conf.position is not None:
            self.frame.SetPosition(self.conf.position)
        else:
            self.frame.Center()

        # Init the frame with no datafile.
        old_conf_data_file = self.conf.data_file
        self._SetDataFile(None)

        # Now, show the frame.
        self.frame.Show(True)
        
        #Disable the diary menu until a diary loaded
        self._DiaryMenuEnable(False)

        # If we were not given a datafile, or the one we were given is
        # invalid, ask for a valid one.
        if self.cmd_datafile or old_conf_data_file:
            self._SetDataFile(self.cmd_datafile or old_conf_data_file)

        # Tell wxWidgets that this is our main window
        self.SetTopWindow(self.frame)
        
        # Return a success flag
        return True

    def _SetFont(self, font):
        """Set the font used by the entry text field."""
        wx.BeginBusyCursor()
        self.ignore_text_event = True
        try:
            self.frame.FindWindowById(self.text_id).SetFont(font)
            self.conf.font_face = font.GetFaceName()
            self.conf.font_size = font.GetPointSize()
            self.options_dialog.FindWindowById(self.font_id).SetLabel(
                "%s, %dpt" % (self.conf.font_face, self.conf.font_size))
        finally:
            self.ignore_text_event = False
            wx.EndBusyCursor()
    
    def _SetDataFile(self, datafile, create=False):
        """Set the active datafile, possible creating one on disk."""
        wx.Yield()
        wx.BeginBusyCursor()
        try:
            self.tree.PruneAll()
            self.tag_tree.PruneAll()
            self._SetEntryModified(False)
            self._SetDiaryModified(False)
            self.panel.Show(False)
            self.conf.data_file = datafile
            if datafile:
                datafile = os.path.abspath(datafile)
                if not os.path.exists(datafile) and not create:
                    wx.MessageBox("Unable to find datafile '%s'." %
                                 (datafile),
                                 "Datafile Missing", wx.OK | wx.ICON_ERROR,
                                 self.frame)
                    return
                elif create:
                    if os.path.exists(datafile):
                        os.remove(datafile)
                    self._SaveData(datafile, None)
                self.frame.SetStatusText('Loading %s...' % datafile)
                try:
                    self.entries = tk_data.parse_data(datafile)
                except tk_data.TKDataVersionException, e:
                    wx.MessageBox("Datafile format used by '%s' is not "
                                 "supported ." % (datafile),
                                 "Datafile Version Error",
                                 wx.OK | wx.ICON_ERROR,
                                 self.frame)
                    return
                timestruct = time.localtime()
    
                def _AddEntryToTree(entry):
                    year, month, day = entry.get_date()
                    id = entry.get_id()
                    self.tree.EntryChangedListener(entry, year, month,
                                                   day, id, False)
                self.entries.enumerate_entries(_AddEntryToTree)
                
                def _AddEntryToTagTree(entry, tag):
                    self.tag_tree.EntryChangedListener(tag, entry, True)
                self.entries.enumerate_tag_entries(_AddEntryToTagTree)
                
                self.tag_tree.CollapseTree()
                self.tree.CollapseTree()
                stack = filter(None, self.tree.GetDateStack(timestruct[0],
                                                            timestruct[1],
                                                            timestruct[2],
                                                            None))
                for item in stack:
                    self.tree.Expand(item)
                self.entries.register_listener(self.tree.EntryChangedListener)
                self.entries.register_listener(self.cal.EntryChangedListener)
                self.entries.register_tag_listener(
                                            self.tag_tree.EntryChangedListener)
                self._SetEntryFormDate(timestruct[0],
                                       timestruct[1],
                                       timestruct[2])
                self.cal.HighlightEvents(self.entries)
                self.panel.Show(True)
                self._DiaryMenuEnable(True)
                self.frame.Layout()
                self._UpdateAuthorBox()
            self.datafile = datafile
            self._SetTitle()
            if create:
                self._FileDiaryOptionsMenu(None)
        finally:
            wx.EndBusyCursor()

    def _SaveData(self, path, entries):
        try:
            tk_data.unparse_data(path, entries)
        except Exception, e:
            wx.MessageBox("Error writing datafile:\n%s" % (str(e)),
                         "Write Error", wx.OK | wx.ICON_ERROR, self.frame)
            raise
            
        
    def _SetTitle(self):
        title = "ThotKeeper%s%s" \
                % (self.datafile and " - " + self.datafile or "",
                   self.entry_modified and " [modified]" or "")
        self.frame.SetTitle(title)
        
    def _UpdateAuthorBox(self):
        show_author = not self.entries.get_author_global()
        self.frame.FindWindowById(self.author_id).Show(show_author)
        self.frame.FindWindowById(self.author_label_id).Show(show_author)
        self.frame.Layout()

    def _RefuseUnsavedModifications(self, refuse_modified_options=False):
        """If there exist unsaved entry modifications, inform the user
        and return True.  Otherwise, return False."""
        if self.entry_modified:
            wx.MessageBox("Entry has been modified.  You must " +
                         "either save or revert it.", "Modified Entry",
                         wx.OK | wx.ICON_INFORMATION, self.frame)
            return True
        elif refuse_modified_options and self.diary_modified:
            if wx.OK == wx.MessageBox("Diary has been modified. Click OK " +
                         "to continue and lose the changes", "Modified Diary",
                         wx.OK| wx.CANCEL | wx.ICON_QUESTION, self.frame):
                return False
            return True
        return False

    def _TextToTags(self, text):
        # Convert tags to lowercase and split by commas
        tags = text.lower().split(',')
        # Split each tag by '/', remove surrounding whitespace, remove empty sections
        # then join back together again
        tags = map(lambda x: '/'.join(
                filter(None, 
                    map(string.strip, 
                        x.split('/')))), tags)
        # Remove any empty tags and return
        return filter(None, tags)
        
    def _TagsToText(self, tags):
        if not tags:
            return ''
        return reduce(lambda x, y: x+', '+y, tags)

    ### FIXME: This function needs a new name
    def _SetEntryFormDate(self, year, month, day, id=-1):
        """Set the data on the entry form."""
        if self._RefuseUnsavedModifications():
            return False
        firstid = self.entries.get_first_id(year, month, day)
        if id == -1:
            id = firstid
        self.entry_form_key = TKEntryKey(year, month, day, id)
        date = wx.DateTime()
        date.ParseFormat("%d-%d-%d 11:59:59" % (year, month, day),
                         '%Y-%m-%d %H:%M:%S', date)
        label = date.Format("%A, %B %d, %Y")
        if firstid is not None and (id is None or id > firstid):
            label += " (%d)" % self.entries.get_id_pos(year, month, day, id)
            self.frame.FindWindowById(self.prev_id).Enable(True)
        else:
            self.frame.FindWindowById(self.prev_id).Enable(False)
        if id is not None:
            self.frame.FindWindowById(self.next_id).Enable(True)
        else:
            self.frame.FindWindowById(self.next_id).Enable(False)
        self.frame.FindWindowById(self.date_id).SetLabel(label)
        text = subject = author = tags = ''
        has_entry = 0
        entry = self.entries.get_entry(year, month, day, id)
        if entry is not None:
            text = entry.get_text()
            author = entry.get_author()
            subject = entry.get_subject()
            tags = self._TagsToText(entry.get_tags())
        self.frame.FindWindowById(self.author_id).SetValue(author)
        self.frame.FindWindowById(self.subject_id).SetValue(subject)
        self.frame.FindWindowById(self.text_id).SetValue(text)
        self.frame.FindWindowById(self.tags_id).SetValue(tags)
        self._TogglePrintMenus(entry and True or False)
        self._SetEntryModified(False)
        
    def _TogglePrintMenus(self, enable=True):
        self.menubar.FindItemById(self.file_print_id).Enable(enable)
        self.menubar.FindItemById(self.file_preview_id).Enable(enable)
        
    def _SetEntryModified(self, enable=True):
        self.entry_modified = enable
        self.menubar.FindItemById(self.file_save_id).Enable(enable or self.diary_modified)
        self.menubar.FindItemById(self.file_revert_id).Enable(enable)
        if self.entry_modified:
            self._TogglePrintMenus(True)
        self._SetTitle()

    def _SetDiaryModified(self, enable=True):
        self.diary_modified = enable
        self.menubar.FindItemById(self.file_save_id).Enable(enable or self.entry_modified)        

    def _FrameClosure(self, event):
        self.frame.SetStatusText("Quitting...")
        self.conf.size = self.frame.GetSize()
        self.conf.position = self.frame.GetPosition()
        if event.CanVeto() and self._RefuseUnsavedModifications(True):
            event.Veto()
        else:
            self.frame.Destroy()
        
    def _CalendarChanged(self, event):
        date = event.GetDate()
        year = date.GetYear()
        month = date.GetMonth() + 1
        day = date.GetDay()
        self._SetEntryFormDate(year, month, day)
        
    def _CalendarDisplayChanged(self, event):
        date = event.GetDate()
        year = date.GetYear()
        month = date.GetMonth() + 1
        has_events = 0
        days = []
        years = self.entries.get_years()
        if year in years:
            months = self.entries.get_months(year)
            if month in months:
                has_events = 1
                days = self.entries.get_days(year, month)
        wx.BeginBusyCursor()
        try:
            for day in range(1, 32):
                if day in days and has_events:
                    self.cal.SetDayAttr(day, True)
                else:
                    self.cal.SetDayAttr(day, False)
            self.cal.Refresh(True)
        finally:
            wx.EndBusyCursor()
        
    def _TodayButtonActivated(self, event):
        timestruct = time.localtime()
        self._SetEntryFormDate(timestruct[0], timestruct[1], timestruct[2])
        
    def _NextButtonActivated(self, event):
        year, month, day, id = self._GetEntryFormKeys()
        nextid = self.entries.get_next_id(year, month, day, id)
        self._SetEntryFormDate(year, month, day, nextid)
      
    def _PrevButtonActivated(self, event):
        year, month, day, id = self._GetEntryFormKeys()
        previd = self.entries.get_prev_id(year, month, day, id)
        self._SetEntryFormDate(year, month, day, previd)
    
    def _EntryDataChanged(self, event):
        if not self.ignore_text_event:
            self._SetEntryModified(True)

    def _TreeActivated(self, event):
        item = event.GetItem()
        tree = event.GetEventObject()
        data = tree.GetItemData(item).GetData()
        if not data.day:
            event.Skip()
            return
        self._SetEntryFormDate(data.year, data.month, data.day, data.id)

    def _GetEntryFormKeys(self):
        ### FIXME: This interface is ... hacky.
        return self.entry_form_key.year, self.entry_form_key.month, \
               self.entry_form_key.day, self.entry_form_key.id

    def _GetEntryFormBits(self):
        year, month, day, id = self._GetEntryFormKeys()
        author = self.frame.FindWindowById(self.author_id).GetValue()
        subject = self.frame.FindWindowById(self.subject_id).GetValue()
        text = self.frame.FindWindowById(self.text_id).GetValue()
        tags = self._TextToTags(
                self.frame.FindWindowById(self.tags_id).GetValue())
        return year, month, day, author, subject, text, id, tags
        
    def _SaveEntriesToPath(self, path=None):
        wx.Yield()
        wx.BeginBusyCursor()
        try:
            if self.entry_modified:
                year, month, day, author, subject, text, id, tags \
                      = self._GetEntryFormBits()
                if id is None:
                    id = self.entries.get_last_id(year, month, day)
                    if id is None:
                        id = 1
                    else:
                        id = id + 1
                    self.entry_form_key = TKEntryKey(year, month, day, id)
                self.entries.store_entry(tk_data.TKEntry(author, subject, text,
                                                         year, month, day,
                                                         id, tags))
            if path is None:
                path = self.conf.data_file
            self._SaveData(path, self.entries)
            if path != self.conf.data_file:
                self._SetDataFile(path, False) 
            self._SetEntryModified(False)
            self._SetDiaryModified(False)
            self.frame.FindWindowById(self.next_id).Enable(True)
        finally:
            wx.EndBusyCursor()

    def _TreeEditMenu(self, event):
        tree = event.GetEventObject().parenttree
        item = tree.GetSelection()
        data = tree.GetItemData(item).GetData()
        if not data.day:
            if data.tag:
                self._RenameTag(data.tag)
            event.Skip()
            return
        self._SetEntryFormDate(data.year, data.month, data.day, data.id)

    def _RenameTag(self, tag):
        rename_tag_box = self.rename_tag_dialog.FindWindowById(self.rename_tag_id)
        rename_tag_box.SetValue(tag)
        if self.rename_tag_dialog.ShowModal() == wx.ID_OK \
                and rename_tag_box.GetValue() != tag:
            self._SetDiaryModified(True)
            def _UpdateSingleTag(current):
                if current==tag:
                    return rename_tag_box.GetValue()
                if current.startswith(tag+'/'):
                    return current.replace(tag, rename_tag_box.GetValue(),1)
                return current
            for en in self.entries.get_entries_by_partial_tag(tag):
                updatedtags = map(_UpdateSingleTag, en.get_tags())
                self.entries.store_entry(tk_data.TKEntry(en.author, en.subject, en.text,
                                                         en.year, en.month, en.day,
                                                         en.id, updatedtags))            
            
    def _TreeDuplicateMenu(self, event):
        item = self.tree.GetSelection()
        tree = event.GetEventObject().parenttree
        data = tree.GetItemData(item).GetData()
        if not data.day:
            wx.MessageBox("This operation is not currently supported.",
                         "Duplication Failed",
                          wx.OK | wx.ICON_ERROR, self.frame)
            return
        new_id = self.entries.get_last_id(data.year, data.month, data.day)
        if new_id is None:
            new_id = 1
        else:
            new_id = new_id + 1
        entry = self.entries.get_entry(data.year, data.month,
                                       data.day, data.id)
        self.entries.store_entry(tk_data.TKEntry(entry.get_author(),
                                                 entry.get_subject(),
                                                 entry.get_text(),
                                                 data.year,
                                                 data.month,
                                                 data.day,
                                                 new_id,
                                                 entry.get_tags()))
        self._SaveData(self.conf.data_file, self.entries)

    def _TreeDeleteMenu(self, event):
        item = self.tree.GetSelection()
        tree = event.GetEventObject().parenttree
        data = tree.GetItemData(item).GetData()
        if not data.day:
            wx.MessageBox("This operation is not currently supported.",
                         "Deletion Failed", wx.OK | wx.ICON_ERROR, self.frame)
            return
        position = self.entries.get_id_pos(data.year, data.month,
                                           data.day, data.id)
        if wx.OK == wx.MessageBox(
            "Are you sure you want to delete the entry for " +
            "%s-%s-%s (%s)?" % (data.year, data.month, data.day, position),
            "Confirm Deletion",
            wx.OK | wx.CANCEL | wx.ICON_QUESTION, self.frame):
            self.entries.remove_entry(data.year, data.month,
                                      data.day, data.id)
            self._SaveData(self.conf.data_file, self.entries)
            dispyear, dispmonth, dispday, dispid = self._GetEntryFormKeys()
            if ((dispyear == data.year) & (dispmonth == data.month) & \
                (dispday == data.day) & (dispid == data.id)):
                self._SetEntryModified(False)
                self._SetEntryFormDate(dispyear, dispmonth, dispday)

    def _TreeExpandMenu(self, event):
        tree = event.GetEventObject().parenttree
        def _ExpandCallback(id):
            tree.Expand(id)
        tree.Walker(_ExpandCallback)
    
    def _TreeCollapseMenu(self, event):
        tree = event.GetEventObject().parenttree
        def _CollapseCallback(id):
            tree.Collapse(id)
        tree.Walker(_CollapseCallback)
    
    def _TreePopup(self, event):
        tree = event.GetEventObject()
        item, flags = tree.HitTest(event.GetPosition())
        popup = self.resources.LoadMenu('TKTreePopup')
        if item and flags & (wx.TREE_HITTEST_ONITEMBUTTON
                             | wx.TREE_HITTEST_ONITEMICON
                             | wx.TREE_HITTEST_ONITEMINDENT
                             | wx.TREE_HITTEST_ONITEMLABEL
                             | wx.TREE_HITTEST_ONITEMRIGHT
                             | wx.TREE_HITTEST_ONITEMSTATEICON):
            if not tree.IsSelected(item):
                tree.SelectItem(item)
            data = tree.GetItemData(item).GetData()
            if not data.day and not data.tag:
                popup.Enable(self.tree_edit_id, False)
                popup.Enable(self.tree_dup_id, False)
                popup.Enable(self.tree_delete_id, False)
        else:
            popup.Enable(self.tree_edit_id, False)
            popup.Enable(self.tree_dup_id, False)
            popup.Enable(self.tree_delete_id, False)
        popup.parenttree = tree
        tree.PopupMenu(popup)
 
    def _GetFileDialog(self, title, directory, flags):
        return wx.FileDialog(self.frame, title, directory, '',
                            'ThotKeeper journal files (*.tkj)|*.tkj', flags)
        
    def _FileNewMenu(self, event):
        if self._RefuseUnsavedModifications(True):
            return False
        directory = '.'
        if os.environ.has_key('HOME'):
            directory = os.environ['HOME']
        if self.conf.data_file is not None:
            directory = os.path.dirname(self.conf.data_file)
        dialog = self._GetFileDialog("Create new data file", directory,
                                     wx.SAVE | wx.OVERWRITE_PROMPT)
        if dialog.ShowModal() == wx.ID_OK:
            path = dialog.GetPath()
            if len(path) < 5 or not path.endswith('.tkj'):
                path = path + '.tkj'
            self._SetDataFile(path, True)
        dialog.Destroy()

    def _FileOpenMenu(self, event):
        if self._RefuseUnsavedModifications(True):
            return False
        directory = '.'
        if os.environ.has_key('HOME'):
            directory = os.environ['HOME']
        if self.conf.data_file is not None:
            directory = os.path.dirname(self.conf.data_file)
        dialog = self._GetFileDialog("Open existing data file", directory,
                                     wx.OPEN)
        if dialog.ShowModal() == wx.ID_OK:
            path = dialog.GetPath()
            self._SetDataFile(path, False)
        dialog.Destroy()

    def _FileSaveMenu(self, event):
        self._SaveEntriesToPath(None)
        
    def _FileSaveAsMenu(self, event):
        directory = os.path.dirname(self.conf.data_file)
        dialog = self._GetFileDialog("Save as a new data file", directory,
                                     wx.SAVE | wx.OVERWRITE_PROMPT)
        if dialog.ShowModal() == wx.ID_OK:
            path = dialog.GetPath()
            if len(path) < 5 or not path.endswith('.tkj'):
                path = path + '.tkj'
            self._SaveEntriesToPath(path)
        dialog.Destroy()

    def _FileRevertMenu(self, event):
        year, month, day, id = self._GetEntryFormKeys()
        self._SetEntryModified(False)
        self._SetEntryFormDate(int(year), int(month), int(day), id)

    def _GetCurrentEntryPieces(self):
        year, month, day, author, subject, text, id, tags \
              = self._GetEntryFormBits()
        date = wx.DateTime()
        date.ParseFormat("%d-%d-%d 11:59:59" % (year, month, day),
                         '%Y-%m-%d %H:%M:%S', date)
        datestr = date.Format("%A, %B %d, %Y")
        return datestr, subject, author, text
        
    def _FilePreviewMenu(self, event):
        try:
            datestr, subject, author, text = self._GetCurrentEntryPieces()
            self.printer.PreviewText(self.datafile, subject, author,
                                     datestr, text)
        except:
            raise
    
    def _FilePrintMenu(self, event):
        try:
            datestr, subject, author, text = self._GetCurrentEntryPieces()
            self.printer.Print(self.datafile, subject, author,
                               datestr, text)
        except:
            pass

    def _FileOptionsMenu(self, event):
        oldfont = self.frame.FindWindowById(self.text_id).GetFont()
        def _ChooseFontButton(event2):
            text = self.frame.FindWindowById(self.text_id)
            font_data = wx.FontData()
            font_data.SetInitialFont(text.GetFont())
            dialog = wx.FontDialog(self.options_dialog, font_data)
            if dialog.ShowModal() == wx.ID_OK:
                font = dialog.GetFontData().GetChosenFont()
                self._SetFont(font)
            dialog.Destroy()
        wx.EVT_BUTTON(self, self.choose_font_id, _ChooseFontButton)
        if self.options_dialog.ShowModal() != wx.ID_OK:
            self._SetFont(oldfont)
        
    def _FileQuitMenu(self, event):
        self.frame.Close()
                 
    def _DiaryMenuEnable(self, enable):
        self.menubar.FindItemById(self.file_diary_options_id).Enable(enable)
        
    def _FileDiaryOptionsMenu(self, event):
        # Grab the controls
        author_name_box = self.frame.FindWindowById(self.author_name_id)
        author_global_radio = self.frame.FindWindowById(self.author_global_id)
        author_per_entry_radio = \
                self.frame.FindWindowById(self.author_per_entry_id)
        # Enable/disable the author name box
        def _ChooseAuthorGlobal(event2):
            author_name_box.Enable(True)
        def _ChooseAuthorPerEntry(event2):
            author_name_box.Enable(False)
        wx.EVT_RADIOBUTTON(self, self.author_global_id, _ChooseAuthorGlobal)
        wx.EVT_RADIOBUTTON(self, self.author_per_entry_id, _ChooseAuthorPerEntry)
        # Set the controls to the current settings
        author_name = self.entries.get_author_name()
        if (author_name == None):
            author_name_box.SetValue("")
        else:
            author_name_box.SetValue(author_name)
        if (self.entries.get_author_global()):
            author_name_box.Enable(True)
            author_global_radio.SetValue(True)
        else:
            author_name_box.Enable(False)
            author_per_entry_radio.SetValue(True)
        if (self.diary_options_dialog.ShowModal() == wx.ID_OK):
            # Save the settings if OK pressed
            if (author_name_box.GetValue() == ""):
                self.entries.set_author_name(None)
            else:
                self.entries.set_author_name(author_name_box.GetValue())
            self.entries.set_author_global(author_global_radio.GetValue())
            self._UpdateAuthorBox() # Show/Hide the author box as needed
            self._SetDiaryModified(True)
        
    def _HelpAboutMenu(self, event):
        wx.MessageBox("ThotKeeper, version %s\n"
                     "A personal daily journal application.\n"
                     "\n"
                     "Copyright (c) 2004-2008 C. Michael Pilato.  "
                     "All rights reserved.\n"
                     "\n"
                     "ThotKeeper is open source software developed "
                     "under the BSD License.  Question, comments, "
                     "and code contributions are welcome.  Visit our "
                     "website: http://www.thotkeeper.org/\n"
                     % (__version__),
                     "About ThotKeeper",
                     wx.OK | wx.CENTER, self.frame)

    def _HelpUpdateMenu(self, event):
        new_version = None
        try:
            new_version, info_url = CheckForUpdates()
        except Exception, e:
            wx.MessageBox("Error occurred while checking for updates:  %s" \
                          % (str(e)),
                          "Update Check", wx.OK | wx.ICON_ERROR, self.frame)
            return
        if new_version is not None:
            wx.MessageBox("A new version (%s) of ThotKeeper is available.\n" \
                          "For more information, visit %s." \
                          % (new_version, info_url),
                          "Update Check", wx.OK, self.frame)
        else:
            wx.MessageBox("This version of ThotKeeper is the latest "
                          "available.",
                          "Update Check", wx.OK, self.frame)
        
    def OnExit(self):
        self.conf.Write()


def main():
    file = None
    argc = len(sys.argv)
    if argc > 1:
        if sys.argv[1] == '--update-check':
            new_version, info_url = CheckForUpdates()
            if new_version is not None:
                print("A new version (%s) of ThotKeeper is available.\n" \
                      "For more information, visit %s." \
                      % (new_version, info_url))
            else:
                print("This version of ThotKeeper is the latest available.")
            return
        else:            
            file = sys.argv[1]
    tk = ThotKeeper(file)
    tk.MainLoop()
    tk.OnExit()
    
