# ThotKeeper -- a personal daily journal application.
#
# Copyright (c) 2004-2021 C. Michael Pilato.  All rights reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE file which can be found at the top level of the ThotKeeper
# distribution.
#
# Website: http://www.thotkeeper.org/

import os
import os.path
import time
import wx
from wx.adv import (GenericCalendarCtrl, CalendarDateAttr)
import wx.xrc
from wx.html import HtmlEasyPrinting
from .version import __version__
from .entries import (TKEntries, TKEntry)
from .parser import (TKDataVersionException, parse_data, unparse_data)


month_names = ['January', 'February', 'March', 'April',
               'May', 'June', 'July', 'August',
               'September', 'October', 'November', 'December']
month_abbrs = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
               'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


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
        conf = wx.Config(style=wx.CONFIG_USE_LOCAL_FILE)
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
        conf = wx.ConfigBase.Get()
        if self.data_file:
            conf.Write(self.CONF_DATA_FILE, self.data_file)
        conf.Write(self.CONF_FONT_NAME, self.font_face)
        conf.WriteInt(self.CONF_FONT_SIZE, self.font_size)
        if self.position:
            conf.Write(self.CONF_POSITION,
                       f'{self.position.x},{self.position.y}')
        if self.size:
            conf.Write(self.CONF_SIZE,
                       f'{self.size.GetWidth()},{self.size.GetHeight()}')
        conf.Flush()


class TKEntryTag:
    """ThotKeeper Entry tag name."""

    def __init__(self, name):
        self.name = (name or '').strip('/')
        self.name_len = len(self.name)

    def __eq__(self, other):
        return self.name == other.name

    def __gt__(self, other):
        # Tag names look like multi-component paths and sort
        # similarly, where children are "greater" than their parents,
        # but less than greater siblings of their parents.  So this
        # algorithm is adapted from Apache Subversion's
        # svn_path_compare_paths() function.

        # Skip past the common prefix of both names.
        min_len = min(self.name_len, other.name_len)
        i = 0
        while (i < min_len) and (self.name[i] == other.name[i]):
            i = i + 1

        # Now compare the first non-common character in both names,
        # treating '/' as a hierarchy separator.  If one doesn't have
        # such a next character,
        self_char = i < self.name_len and self.name[i] or '\0'
        other_char = i < other.name_len and other.name[i] or '\0'
        if self_char == '/' and i == other.name_len:
            return False
        if other_char == '/' and i == self.name_len:
            return True
        if self_char == '/' and i < self.name_len:
            return True
        if other_char == '/' and i < other.name_len:
            return False
        return self_char < other_char


class TKEntryKey:
    def __init__(self, year, month, day, id, tag=None):
        self.year = year
        self.month = month
        self.day = day
        self.id = id
        self.tag = TKEntryTag(tag)

    def __eq__(self, other):
        return ([self.tag, self.year, self.month, self.day, self.id] ==
                [other.tag, other.year, other.month, other.day, other.id])

    def __lt__(self, other):
        if self.year is not None and other.year is None:
            return True
        if self.year is None and other.year is not None:
            return False
        return ([self.tag, self.year, self.month, self.day, self.id] <
                [other.tag, other.year, other.month, other.day, other.id])


class TKTreeCtrl(wx.TreeCtrl):
    def __init__(self, parent, style):
        wx.TreeCtrl.__init__(self, parent=parent, style=style)

    def GetRootId(self):
        return self.root_id

    def OnCompareItems(self, item1, item2):
        data1 = self.GetItemData(item1)
        data2 = self.GetItemData(item2)
        if data1 is None or data2 is None:
            return 0
        return (data2 > data1) - (data2 < data1)  # py3 shim for cmp()

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
            child_data = self.GetItemData(child_id)
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


class TKEventTree(TKTreeCtrl):
    def __init__(self, parent, style):
        TKTreeCtrl.__init__(self, parent, style)
        root_data = TKEntryKey(None, None, None, None)
        self.root_id = self.AddRoot('ThotKeeper Entries', -1, -1, root_data)

    def GetDateStack(self, year, month, day, id):
        stack = []
        root_id = self.GetRootItem()
        stack.append(root_id)  # depth=0
        item_id = self.FindChild(root_id,
                                 TKEntryKey(year, None, None, None))
        stack.append(item_id)  # depth=1
        if item_id:
            item_id = self.FindChild(item_id,
                                     TKEntryKey(year, month, None, None))
            stack.append(item_id)  # depth=2
            if item_id:
                item_id = self.FindChild(item_id,
                                         TKEntryKey(year, month, day, id))
                stack.append(item_id)  # depth=3
            else:
                stack.append(None)  # depth=3
        else:
            stack.append(None)  # depth=2
            stack.append(None)  # depth=3
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
                    data = TKEntryKey(year, None, None, None)
                    stack[1] = self.AppendItem(stack[0],
                                               str(year),
                                               -1, -1, data)
                    self.SortChildren(stack[0])
                if not stack[2]:
                    data = TKEntryKey(year, month, None, None)
                    stack[2] = self.AppendItem(stack[1],
                                               month_names[month - 1],
                                               -1, -1, data)
                    self.SortChildren(stack[1])
                if not stack[3]:
                    data = TKEntryKey(year, month, day, id)
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


class TKEventTagTree(TKTreeCtrl):
    """Event Tree (ordered by tags)"""

    def __init__(self, parent, style):
        TKTreeCtrl.__init__(self, parent, style)
        root_data = TKEntryKey(None, None, None, None)
        self.root_id = self.AddRoot('ThotKeeper Tags', -1, -1, root_data)

    def GetTagStack(self, tag, year, month, day, id):
        """Return a list of tree item id's, the path of such from the
        root of the tree to the requested item.  If any segment of the
        expected path is missing, the list will be truncated to only
        those segments which exist."""

        tag_path = list(map(str, tag.split('/')))
        stack = []
        prev_id = root_id = self.GetRootItem()
        stack.append(root_id)  # depth=0
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
            stack.append(item_id)  # depth=1, depth=2, ...
            prev_id = item_id
        item_id = self.FindChild(prev_id,
                                 TKEntryKey(year, month, day, id, tag))
        if item_id:
            stack.append(item_id)  # depth=-1
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
            tag_path = list(map(str, tag.split('/')))
            expected_stack_len = len(tag_path) + 2  # root + tag pieces + entry
            if not add:
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
                        data = TKEntryKey(None, None, None, None, newtag)
                        stack.append(self.AppendItem(stack[i], tag_path[i],
                                                     -1, -1, data))
                        self.SortChildren(stack[i])
                subject = entry.get_subject()
                if len(stack) == i + 2:
                    data = TKEntryKey(year, month, day, id, newtag)
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


class TKEventCal(GenericCalendarCtrl):
    def SetDayAttr(self, day, has_event):
        if has_event:
            attr = CalendarDateAttr()
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


class TKEntryPrinter(HtmlEasyPrinting):
    def __init__(self):
        HtmlEasyPrinting.__init__(self)

    def Print(self, filename, title, author, date, text):
        self.PrintText(self._HTMLize(title, author, date, text), filename)

    def PreviewText(self, filename, title, author, date, text):
        HtmlEasyPrinting.PreviewText(self, self._HTMLize(title, author,
                                                         date, text))

    def _HTMLize(self, title, author, date, text):
        title = title or '(no title)'
        author = author or '(no author)'
        date = date or '(no date)'
        paragraphs = ''.join(['<p align="justify">' + x + '</p>\n'
                              for x in text.split('\n')])
        return (f'<html><body>'
                f'<h2>{title}</h2>'
                f'<p><i>by <b>{author}</b>, on <b>{date}</b></i></p>'
                f'{paragraphs}'
                f'</body></html>')


class ThotKeeper(wx.App):
    def __init__(self, datafile=None):
        self.cmd_datafile = datafile
        self.datafile = None
        wx.App.__init__(self)

    # -----------------------------------------------------------------
    # Core wx.App Interfaces
    # -----------------------------------------------------------------

    def OnInit(self):
        """wxWidgets calls this method to initialize the application"""

        # Who am I?
        self.SetVendorName("Red-Bean Software")
        self.SetAppName("ThotKeeper")

        # Get our persisted options into an easily addressable object.
        self.conf = TKOptions()
        self.conf.Read()

        # Get the XML Resource class.
        resource_path = os.path.join(os.path.dirname(__file__),
                                     'resources.xrc')
        self.resources = wx.xrc.XmlResource(resource_path)

        # Store a bunch of resource IDs for easier access.
        self.calendar_id = self._GetXRCID('TKCalendar')
        self.datetree_id = self._GetXRCID('TKDateTree')
        self.tagtree_id = self._GetXRCID('TKTagTree')
        self.today_id = self._GetXRCID('TKToday')
        self.next_id = self._GetXRCID('TKNext')
        self.prev_id = self._GetXRCID('TKPrev')
        self.date_id = self._GetXRCID('TKEntryDate')
        self.author_id = self._GetXRCID('TKEntryAuthor')
        self.author_label_id = self._GetXRCID('TKEntryAuthorLabel')
        self.subject_id = self._GetXRCID('TKEntrySubject')
        self.tags_id = self._GetXRCID('TKEntryTags')
        self.text_id = self._GetXRCID('TKEntryText')
        self.file_new_id = self._GetXRCID('TKMenuFileNew')
        self.file_open_id = self._GetXRCID('TKMenuFileOpen')
        self.file_save_id = self._GetXRCID('TKMenuFileSave')
        self.file_saveas_id = self._GetXRCID('TKMenuFileSaveAs')
        self.file_archive_id = self._GetXRCID('TKMenuFileArchive')
        self.file_revert_id = self._GetXRCID('TKMenuFileRevert')
        self.file_options_id = self._GetXRCID('TKMenuFileOptions')
        self.file_diary_options_id = self._GetXRCID('TKMenuFileDiaryOptions')
        self.file_quit_id = self._GetXRCID('TKMenuFileQuit')
        self.entry_new_id = self._GetXRCID('TKMenuEntryNew')
        self.entry_new_today_id = self._GetXRCID('TKMenuEntryNewToday')
        self.entry_duplicate_id = self._GetXRCID('TKMenuEntryDuplicate')
        self.entry_redate_id = self._GetXRCID('TKMenuEntryRedate')
        self.entry_delete_id = self._GetXRCID('TKMenuEntryDelete')
        self.entry_preview_id = self._GetXRCID('TKMenuEntryPreview')
        self.entry_print_id = self._GetXRCID('TKMenuEntryPrint')
        self.help_update_id = self._GetXRCID('TKMenuHelpUpdate')
        self.help_about_id = self._GetXRCID('TKMenuHelpAbout')
        self.open_tool_id = self._GetXRCID('TKToolOpen')
        self.choose_font_id = self._GetXRCID('TKChooseFontButton')
        self.font_id = self._GetXRCID('TKFontName')
        self.author_global_id = self._GetXRCID('TKAuthorGlobal')
        self.author_name_id = self._GetXRCID('TKAuthorName')
        self.author_per_entry_id = self._GetXRCID('TKAuthorPerEntry')
        self.tree_edit_id = self._GetXRCID('TKTreeMenuEdit')
        self.tree_redate_id = self._GetXRCID('TKTreeMenuRedate')
        self.tree_dup_id = self._GetXRCID('TKTreeMenuDuplicate')
        self.tree_delete_id = self._GetXRCID('TKTreeMenuDelete')
        self.tree_expand_id = self._GetXRCID('TKTreeMenuExpand')
        self.tree_collapse_id = self._GetXRCID('TKTreeMenuCollapse')
        self.rename_tag_id = self._GetXRCID('TKTagName')

        # Construct our datafile parser and placeholder for data.
        self.entries = None

        # Setup a printer object.
        self.printer = TKEntryPrinter()

        # Note that we have no outstanding data modifications.
        self.entry_modified = False
        self.diary_modified = False

        # We are not currently ignoring text events.
        self.ignore_text_event = False

        # Fetch our main frame.
        self.frame = self.resources.LoadFrame(None, 'TKFrame')

        # Fetch our panels.
        self.panel = self.frame.FindWindowById(
            self.resources.GetXRCID('TKPanel'))
        self.date_panel = self.frame.FindWindowById(
            self.resources.GetXRCID('TKDatePanel'))

        # Fetch our options dialog.
        self.options_dialog = self.resources.LoadDialog(self.frame,
                                                        'TKOptions')

        # Fetch the per-diary options dialog
        self.diary_options_dialog = self.resources.LoadDialog(self.frame,
                                                              'TKDiaryOptions')

        # Fetch the rename tag dialog
        self.rename_tag_dialog = self.resources.LoadDialog(self.frame,
                                                           'TKTagRename')

        # Fetch (and assign) our menu bar.
        self.menubar = self.resources.LoadMenuBar('TKMenuBar')
        self.frame.SetMenuBar(self.menubar)

        # Create a status bar.import locale
        self.statusbar = self.frame.CreateStatusBar(2)
        self.statusbar.SetStatusWidths([-1, 100])

        # Replace "unknown" XRC placeholders with custom widgets.
        self.cal = TKEventCal(parent=self.date_panel,
                              style=wx.adv.CAL_SEQUENTIAL_MONTH_SELECTION)
        self.resources.AttachUnknownControl('TKCalendar',
                                            self.cal, self.date_panel)
        tree = TKEventTree(parent=self.panel,
                           style=wx.TR_HAS_BUTTONS)
        self.resources.AttachUnknownControl('TKDateTree',
                                            tree, self.panel)
        tagtree = TKEventTagTree(parent=self.panel,
                                 style=wx.TR_HAS_BUTTONS)
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
        self.frame.Bind(wx.EVT_CLOSE, self._FrameClosure)
        self.Bind(wx.EVT_BUTTON, self._TodayButtonActivated,
                  id=self.today_id)
        self.Bind(wx.EVT_BUTTON, self._NextButtonActivated,
                  id=self.next_id)
        self.Bind(wx.EVT_BUTTON, self._PrevButtonActivated,
                  id=self.prev_id)
        self.Bind(wx.EVT_TEXT, self._EntryDataChanged,
                  id=self.text_id)
        self.Bind(wx.EVT_TEXT, self._EntryDataChanged,
                  id=self.author_id)
        self.Bind(wx.EVT_TEXT, self._EntryDataChanged,
                  id=self.tags_id)
        self.Bind(wx.EVT_TEXT, self._EntryDataChanged,
                  id=self.subject_id)
        self.Bind(wx.adv.EVT_CALENDAR, self._CalendarChanged,
                  id=self.calendar_id)
        self.Bind(wx.adv.EVT_CALENDAR_YEAR, self._CalendarDisplayChanged,
                  id=self.calendar_id)
        self.Bind(wx.adv.EVT_CALENDAR_MONTH, self._CalendarDisplayChanged,
                  id=self.calendar_id)
        self.Bind(wx.EVT_MENU, self._FileNewMenu,
                  id=self.file_new_id)
        self.Bind(wx.EVT_MENU, self._FileOpenMenu,
                  id=self.file_open_id)
        self.Bind(wx.EVT_MENU, self._FileSaveMenu,
                  id=self.file_save_id)
        self.Bind(wx.EVT_MENU, self._FileSaveAsMenu,
                  id=self.file_saveas_id)
        self.Bind(wx.EVT_MENU, self._FileArchiveMenu,
                  id=self.file_archive_id)
        self.Bind(wx.EVT_MENU, self._FileRevertMenu,
                  id=self.file_revert_id)
        self.Bind(wx.EVT_MENU, self._FileDiaryOptionsMenu,
                  id=self.file_diary_options_id)
        self.Bind(wx.EVT_MENU, self._FileOptionsMenu,
                  id=self.file_options_id)
        self.Bind(wx.EVT_MENU, self._FileQuitMenu,
                  id=self.file_quit_id)
        self.Bind(wx.EVT_MENU, self._EntryNewMenu,
                  id=self.entry_new_id)
        self.Bind(wx.EVT_MENU, self._EntryNewTodayMenu,
                  id=self.entry_new_today_id)
        self.Bind(wx.EVT_MENU, self._EntryDuplicateMenu,
                  id=self.entry_duplicate_id)
        self.Bind(wx.EVT_MENU, self._EntryRedateMenu,
                  id=self.entry_redate_id)
        self.Bind(wx.EVT_MENU, self._EntryDeleteMenu,
                  id=self.entry_delete_id)
        self.Bind(wx.EVT_MENU, self._EntryPreviewMenu,
                  id=self.entry_preview_id)
        self.Bind(wx.EVT_MENU, self._EntryPrintMenu,
                  id=self.entry_print_id)
        self.Bind(wx.EVT_MENU, self._HelpUpdateMenu,
                  id=self.help_update_id)
        self.Bind(wx.EVT_MENU, self._HelpAboutMenu,
                  id=self.help_about_id)

        # Event handlers for the Tree widget.
        self.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self._TreeActivated,
                  id=self.datetree_id)
        self.tree.Bind(wx.EVT_RIGHT_DOWN, self._TreePopup)
        self.tree.Bind(wx.EVT_MENU, self._TreeEditMenu,
                       id=self.tree_edit_id)
        self.tree.Bind(wx.EVT_MENU, self._TreeChangeDateMenu,
                       id=self.tree_redate_id)
        self.tree.Bind(wx.EVT_MENU, self._TreeDuplicateMenu,
                       id=self.tree_dup_id)
        self.tree.Bind(wx.EVT_MENU, self._TreeDeleteMenu,
                       id=self.tree_delete_id)
        self.tree.Bind(wx.EVT_MENU, self._TreeExpandMenu,
                       id=self.tree_expand_id)
        self.tree.Bind(wx.EVT_MENU, self._TreeCollapseMenu,
                       id=self.tree_collapse_id)

        # Event handlers for the Tag Tree widget.
        self.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self._TreeActivated,
                  id=self.tagtree_id)
        self.tag_tree.Bind(wx.EVT_RIGHT_DOWN, self._TreePopup)
        self.tag_tree.Bind(wx.EVT_MENU, self._TreeEditMenu,
                           id=self.tree_edit_id)
        self.tag_tree.Bind(wx.EVT_MENU, self._TreeChangeDateMenu,
                           id=self.tree_redate_id)
        self.tag_tree.Bind(wx.EVT_MENU, self._TreeDuplicateMenu,
                           id=self.tree_dup_id)
        self.tag_tree.Bind(wx.EVT_MENU, self._TreeDeleteMenu,
                           id=self.tree_delete_id)
        self.tag_tree.Bind(wx.EVT_MENU, self._TreeExpandMenu,
                           id=self.tree_expand_id)
        self.tag_tree.Bind(wx.EVT_MENU, self._TreeCollapseMenu,
                           id=self.tree_collapse_id)

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

        # Disable the diary menu until a diary loaded
        self._DiaryMenuEnable(False)

        # If we were not given a datafile, or the one we were given is
        # invalid, ask for a valid one.
        if self.cmd_datafile or old_conf_data_file:
            self._SetDataFile(self.cmd_datafile or old_conf_data_file)

        # Tell wxWidgets that this is our main window
        self.SetTopWindow(self.frame)

        # Return a success flag
        return True

    def OnExit(self):
        self.conf.Write()
        return wx.App.OnExit(self)

    # -----------------------------------------------------------------
    # Utility Functions
    # -----------------------------------------------------------------

    def _GetXRCID(self, resource_name):
        return self.resources.GetXRCID(resource_name)

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
                    wx.MessageBox(f'Unable to find datafile "{datafile}".',
                                  'Datafile Missing',
                                  wx.OK | wx.ICON_ERROR,
                                  self.frame)
                    return
                elif create:
                    if os.path.exists(datafile):
                        os.remove(datafile)
                    self._SaveData(datafile, None)
                self.frame.SetStatusText('Loading %s...' % datafile)
                try:
                    self.entries = parse_data(datafile)
                except TKDataVersionException:
                    wx.MessageBox((f'Datafile format used by "{datafile}" is '
                                   f'not supported.'),
                                  'Datafile Version Error',
                                  wx.OK | wx.ICON_ERROR,
                                  self.frame)
                    return
                finally:
                    self.frame.SetStatusText('')
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
                stack = [_f for _f in self.tree.GetDateStack(timestruct[0],
                                                             timestruct[1],
                                                             timestruct[2],
                                                             None) if _f]
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
            unparse_data(path, entries)
        except Exception as e:
            wx.MessageBox(f'Error writing datafile:\n{e}',
                          'Write Error',
                          wx.OK | wx.ICON_ERROR,
                          self.frame)
            raise

    def _RefuseUnsavedModifications(self, refuse_modified_options=False):
        """If there exist unsaved entry modifications, inform the user
        and return True.  Otherwise, return False."""
        if self.entry_modified:
            wx.MessageBox(('Entry has been modified.  You must either '
                           'save or revert it.'),
                          'Modified Entry',
                          wx.OK | wx.ICON_INFORMATION,
                          self.frame)
            return True
        elif refuse_modified_options and self.diary_modified:
            if wx.OK == wx.MessageBox(('Diary has been modified.  Click OK '
                                       'to continue and lose the changes.'),
                                      'Modified Diary',
                                      wx.OK | wx.CANCEL | wx.ICON_QUESTION,
                                      self.frame):
                return False
            return True
        return False

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

    def _TextToTags(self, text):
        # Convert tags string to lowercase and split by commas, then
        # cleanup each tag (splitting on '/', stripping, removing
        # empty sections, and rejoining).
        tags = []
        for tag in text.lower().split(','):
            tag = '/'.join([x.strip() for x in tag.split('/')])
            if tag:
                tags.append(tag)
        return tags

    def _TagsToText(self, tags):
        return tags and ', '.join(tags) or ''

    # FIXME: This function needs a new name
    def _SetEntryFormDate(self, year, month, day, id=-1):
        """Set the data on the entry form."""
        if self._RefuseUnsavedModifications():
            return False

        date = self._MakeDateTime(year, month, day)
        self.cal.SetDate(date)
        firstid = self.entries.get_first_id(year, month, day)
        if id == -1:
            id = firstid
        self.entry_form_key = TKEntryKey(year, month, day, id)
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
        entry = self.entries.get_entry(year, month, day, id)
        if entry is not None:
            text = entry.get_text()
            author = entry.get_author()
            subject = entry.get_subject()
            tags = ', '.join(entry.get_tags() or [])
        self.frame.FindWindowById(self.author_id).SetValue(author)
        self.frame.FindWindowById(self.subject_id).SetValue(subject)
        self.frame.FindWindowById(self.text_id).SetValue(text)
        self.frame.FindWindowById(self.tags_id).SetValue(tags)
        self._NotifyEntryLoaded(entry and True or False)

    def _NotifyEntryLoaded(self, is_loaded=True):
        self._ToggleEntryMenus(is_loaded)
        self._SetEntryModified(False)

    def _ToggleEntryMenus(self, is_loaded=True):
        self.menubar.FindItemById(self.entry_duplicate_id).Enable(is_loaded)
        self.menubar.FindItemById(self.entry_redate_id).Enable(is_loaded)
        self.menubar.FindItemById(self.entry_delete_id).Enable(is_loaded)
        self.menubar.FindItemById(self.entry_print_id).Enable(is_loaded)
        self.menubar.FindItemById(self.entry_preview_id).Enable(is_loaded)

    def _SetEntryModified(self, enable=True):
        self.entry_modified = enable
        self.menubar.FindItemById(self.file_save_id).Enable(
            enable or self.diary_modified)
        self.menubar.FindItemById(self.file_revert_id).Enable(enable)
        if self.entry_modified:
            self._ToggleEntryMenus(True)
        self._SetTitle()

    def _SetDiaryModified(self, enable=True):
        self.diary_modified = enable
        self.menubar.FindItemById(self.file_save_id).Enable(
            enable or self.entry_modified)

    def _GetEntryFormKeys(self):
        # FIXME: This interface is ... hacky.
        return (self.entry_form_key.year,
                self.entry_form_key.month,
                self.entry_form_key.day,
                self.entry_form_key.id)

    def _GetEntryFormBits(self):
        year, month, day, id = self._GetEntryFormKeys()
        author = self.frame.FindWindowById(self.author_id).GetValue()
        subject = self.frame.FindWindowById(self.subject_id).GetValue()
        text = self.frame.FindWindowById(self.text_id).GetValue()
        tags = self._TextToTags(
            self.frame.FindWindowById(self.tags_id).GetValue())
        return year, month, day, author, subject, text, id, tags

    def _GetFileDialog(self, title, flags, basename=''):
        directory = '.'
        if 'HOME' in os.environ:
            directory = os.environ['HOME']
        if self.conf.data_file is not None:
            directory = os.path.dirname(self.conf.data_file)
        return wx.FileDialog(self.frame, title, directory, basename,
                             'ThotKeeper journal files (*.tkj)|*.tkj',
                             flags)

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
                self.entries.store_entry(TKEntry(author, subject, text,
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

    def _RenameTag(self, tag):
        rename_tag_box = self.rename_tag_dialog.FindWindowById(
            self.rename_tag_id)
        rename_tag_box.SetValue(tag)
        if self.rename_tag_dialog.ShowModal() == wx.ID_OK \
                and rename_tag_box.GetValue() != tag:
            self._SetDiaryModified(True)

            def _UpdateSingleTag(current):
                if current == tag:
                    return rename_tag_box.GetValue()
                if current.startswith(tag + '/'):
                    return current.replace(tag, rename_tag_box.GetValue(), 1)
                return current
            for en in self.entries.get_entries_by_partial_tag(tag):
                updatedtags = list(map(_UpdateSingleTag, en.get_tags()))
                self.entries.store_entry(TKEntry(en.author, en.subject,
                                                 en.text, en.year,
                                                 en.month, en.day,
                                                 en.id, updatedtags))

    def _QueryChooseDate(self, title, default_date=None):
        # Fetch the date selection dialog, and replace the "unknown" XRC
        # placeholder with a calendar widget.
        choose_date_dialog = self.resources.LoadDialog(self.frame,
                                                       'TKChooseDate')
        choose_date_dialog.SetTitle(title)
        choose_date_panel = choose_date_dialog.FindWindowById(
            self._GetXRCID('TKChooseDatePanel'))
        choose_date_cal = wx.adv.GenericCalendarCtrl(
            parent=choose_date_panel,
            style=wx.adv.CAL_SEQUENTIAL_MONTH_SELECTION)
        self.resources.AttachUnknownControl('TKChooseDateCalendar',
                                            choose_date_cal,
                                            choose_date_panel)
        choose_date_cal_id = self._GetXRCID('TKChooseDateCalendar')
        choose_date_today_id = self._GetXRCID('TKChooseDateToday')

        # Ask the user to select a date.  We'll hook in a couple of
        # custom event handlers here:  one catches double-clicks on the
        # calendar as dialog-close-worthy events, and the other allows
        # the dialog's "Today" button to set the dialog's selected
        # calendar day.

        def _ChooseDateCalendarChanged(event):
            event.Skip()
            choose_date_dialog.EndModal(wx.ID_OK)
        self.Bind(wx.adv.EVT_CALENDAR, _ChooseDateCalendarChanged,
                  id=choose_date_cal_id)

        def _ChooseDateTodayClicked(event):
            timestruct = time.localtime()
            date = self._MakeDateTime(timestruct[0],
                                      timestruct[1],
                                      timestruct[2])
            choose_date_cal.SetDate(date)
        self.Bind(wx.EVT_BUTTON, _ChooseDateTodayClicked,
                  id=choose_date_today_id)

        if not default_date:
            timestruct = time.localtime()
            default_date = self._MakeDateTime(timestruct[0],
                                              timestruct[1],
                                              timestruct[2])
        choose_date_cal.SetDate(default_date)
        if choose_date_dialog.ShowModal() != wx.ID_OK:
            choose_date_dialog.Destroy()
            return None
        date = choose_date_cal.GetDate()
        choose_date_dialog.Destroy()
        return date

    def _RedateEntry(self, year, month, day, id):
        if self._RefuseUnsavedModifications(True):
            return False
        entry = self.entries.get_entry(year, month, day, id)

        date = self._QueryChooseDate('Select new entry date',
                                     self._MakeDateTime(year, month, day))
        if date is None:
            return
        new_year = date.GetYear()
        new_month = date.GetMonth() + 1
        new_day = date.GetDay()
        if [new_year, new_month, new_day] != [year, month, day]:
            # Save the entry as the last item on the new date, and delete
            # the original entry.
            new_id = self.entries.get_last_id(new_year, new_month, new_day)
            if new_id is None:
                new_id = 1
            else:
                new_id = new_id + 1
            self.entries.store_entry(TKEntry(entry.get_author(),
                                             entry.get_subject(),
                                             entry.get_text(),
                                             new_year,
                                             new_month,
                                             new_day,
                                             new_id,
                                             entry.get_tags()))
            self.entries.remove_entry(year, month, day, id)
            self._SaveData(self.conf.data_file, self.entries)
            self._SetEntryFormDate(new_year, new_month, new_day, new_id)

    def _DuplicateEntry(self, year, month, day, id):
        if self._RefuseUnsavedModifications(True):
            return False
        new_id = self.entries.get_last_id(year, month, day)
        if new_id is None:
            new_id = 1
        else:
            new_id = new_id + 1
        entry = self.entries.get_entry(year, month, day, id)
        self.entries.store_entry(TKEntry(entry.get_author(),
                                         entry.get_subject(),
                                         entry.get_text(),
                                         year,
                                         month,
                                         day,
                                         new_id,
                                         entry.get_tags()))
        self._SaveData(self.conf.data_file, self.entries)
        self._SetEntryFormDate(year, month, day, new_id)

    def _DeleteEntry(self, year, month, day, id, skip_verify=False):
        if self._RefuseUnsavedModifications(True):
            return False
        entry = self.entries.get_entry(year, month, day, id)

        def _ConfirmDelete():
            return wx.MessageBox(
                ("Are you sure you want to delete this entry?\n\n"
                 "   Date: %04d-%02d-%02d\n"
                 "   Author: %s\n"
                 "   Subject:  %s\n"
                 "   Tags: %s"
                 % (year, month, day, entry.get_author(),
                    entry.get_subject(),
                    self._TagsToText(entry.get_tags()))),
                'Confirm Deletion',
                wx.OK | wx.CANCEL | wx.ICON_QUESTION,
                self.frame)
        if skip_verify or wx.OK == _ConfirmDelete():
            self.entries.remove_entry(year, month, day, id)
            self._SaveData(self.conf.data_file, self.entries)
            dispyear, dispmonth, dispday, dispid = self._GetEntryFormKeys()
            if [dispyear, dispmonth, dispday, dispid] == \
               [year, month, day, id]:
                self._SetEntryModified(False)
                self._SetEntryFormDate(dispyear, dispmonth, dispday)

    def _MakeDateTime(self, year, month, day):
        date = wx.DateTime()
        date.ParseFormat("%d-%d-%d 11:59:59" % (year, month, day),
                         '%Y-%m-%d %H:%M:%S', date)
        return date

    def _GetCurrentEntryPieces(self):
        year, month, day, author, subject, text, id, tags = \
            self._GetEntryFormBits()
        date = self._MakeDateTime(year, month, day)
        datestr = date.Format("%A, %B %d, %Y")
        return datestr, subject, author, text

    def _DiaryMenuEnable(self, enable):
        self.menubar.FindItemById(self.file_diary_options_id).Enable(enable)

    def _ArchiveEntriesBeforeDate(self, archive_path, year, month, day):
        if self._RefuseUnsavedModifications(True):
            return False

        # First, clone the entries older than YEAR/MONTH/DAY.
        new_entries = TKEntries()

        def _CloneEntryCB(entry):
            entry_year, entry_month, entry_day = entry.get_date()
            if ((entry_year < year) or
                (entry_year == year and entry_month < month) or
                ([entry_year, entry_month] == [year, month] and
                 entry_day < day)):
                new_entries.store_entry(entry)
        self.entries.enumerate_entries(_CloneEntryCB)

        # Now write those suckers to a new place.
        self._SaveData(archive_path, new_entries)

        # Finally, delete the old entries from the current set.
        def _DeleteEntryCB(entry):
            entry_year, entry_month, entry_day = entry.get_date()
            entry_id = entry.get_id()
            self._DeleteEntry(entry_year, entry_month, entry_day, entry_id,
                              skip_verify=True)
        new_entries.enumerate_entries(_DeleteEntryCB)

    # -----------------------------------------------------------------
    # Tree Popup Menu Actions
    # -----------------------------------------------------------------

    def _TreeEditMenu(self, event):
        tree = event.GetEventObject().parenttree
        item = tree.GetSelection()
        data = tree.GetItemData(item)
        if not data.day:
            if data.tag:
                self._RenameTag(data.tag)
            event.Skip()
            return
        self._SetEntryFormDate(data.year, data.month, data.day, data.id)

    def _TreeChangeDateMenu(self, event):
        tree = event.GetEventObject().parenttree
        item = tree.GetSelection()
        data = tree.GetItemData(item)
        if not data.day:
            wx.MessageBox('This operation is not currently supported.',
                          'Entry Date Change Failed',
                          wx.OK | wx.ICON_ERROR,
                          self.frame)
            return
        self._RedateEntry(data.year, data.month, data.day, data.id)

    def _TreeDuplicateMenu(self, event):
        item = self.tree.GetSelection()
        tree = event.GetEventObject().parenttree
        data = tree.GetItemData(item)
        if not data.day:
            wx.MessageBox('This operation is not currently supported.',
                          'Duplication Failed',
                          wx.OK | wx.ICON_ERROR,
                          self.frame)
            return
        self._DuplicateEntry(data.year, data.month, data.day, data.id)

    def _TreeDeleteMenu(self, event):
        item = self.tree.GetSelection()
        tree = event.GetEventObject().parenttree
        data = tree.GetItemData(item)
        if not data.day:
            wx.MessageBox('This operation is not currently supported.',
                          'Deletion Failed',
                          wx.OK | wx.ICON_ERROR,
                          self.frame)
            return
        self._DeleteEntry(data.year, data.month, data.day, data.id)

    def _TreeExpandMenu(self, event):
        tree = event.GetEventObject().parenttree
        tree.Walker(tree.Expand)

    def _TreeCollapseMenu(self, event):
        tree = event.GetEventObject().parenttree
        tree.Walker(tree.Collapse)

    def _TreePopup(self, event):
        tree = event.GetEventObject()
        item, flags = tree.HitTest(event.GetPosition())
        popup = self.resources.LoadMenu('TKTreePopup')
        if item and flags & (wx.TREE_HITTEST_ONITEMBUTTON |
                             wx.TREE_HITTEST_ONITEMICON |
                             wx.TREE_HITTEST_ONITEMINDENT |
                             wx.TREE_HITTEST_ONITEMLABEL |
                             wx.TREE_HITTEST_ONITEMRIGHT |
                             wx.TREE_HITTEST_ONITEMSTATEICON):
            if not tree.IsSelected(item):
                tree.SelectItem(item)
            data = tree.GetItemData(item)
            if not data.day and not data.tag:
                popup.Enable(self.tree_edit_id, False)
                popup.Enable(self.tree_redate_id, False)
                popup.Enable(self.tree_dup_id, False)
                popup.Enable(self.tree_delete_id, False)
        else:
            popup.Enable(self.tree_edit_id, False)
            popup.Enable(self.tree_redate_id, False)
            popup.Enable(self.tree_dup_id, False)
            popup.Enable(self.tree_delete_id, False)
        popup.parenttree = tree
        tree.PopupMenu(popup)

    # -----------------------------------------------------------------
    # Main Menu Actions
    # -----------------------------------------------------------------

    def _FileNewMenu(self, event):
        if self._RefuseUnsavedModifications(True):
            return False
        dialog = self._GetFileDialog("Create new data file",
                                     wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dialog.ShowModal() == wx.ID_OK:
            path = dialog.GetPath()
            if len(path) < 5 or not path.endswith('.tkj'):
                path = path + '.tkj'
            self._SetDataFile(path, True)
        dialog.Destroy()

    def _FileOpenMenu(self, event):
        if self._RefuseUnsavedModifications(True):
            return False
        dialog = self._GetFileDialog("Open existing data file",
                                     wx.FD_OPEN)
        if dialog.ShowModal() == wx.ID_OK:
            path = dialog.GetPath()
            self._SetDataFile(path, False)
        dialog.Destroy()

    def _FileSaveMenu(self, event):
        self._SaveEntriesToPath(None)

    def _FileSaveAsMenu(self, event):
        dialog = self._GetFileDialog('Save as a new data file',
                                     wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dialog.ShowModal() == wx.ID_OK:
            path = dialog.GetPath()
            if len(path) < 5 or not path.endswith('.tkj'):
                path = path + '.tkj'
            self._SaveEntriesToPath(path)
        dialog.Destroy()

    def _FileArchiveMenu(self, event):
        date = self._QueryChooseDate('Archive files before which date?')
        if date is None:
            return

        path = None
        new_basename = ''
        if self.conf.data_file is not None:
            new_base, new_ext = os.path.splitext(os.path.basename(
                self.conf.data_file))
            if not new_ext:
                new_ext = '.tkj'
            new_basename = new_base + '.archive' + new_ext
        dialog = self._GetFileDialog('Archive to a new data file',
                                     wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
                                     new_basename)
        if dialog.ShowModal() == wx.ID_OK:
            path = dialog.GetPath()
        dialog.Destroy()
        if path is None:
            return

        if len(path) < 5 or not path.endswith('.tkj'):
            path = path + '.tkj'
        wx.Yield()
        wx.BeginBusyCursor()
        try:
            self._ArchiveEntriesBeforeDate(path,
                                           date.GetYear(),
                                           date.GetMonth() + 1,
                                           date.GetDay())
        finally:
            wx.EndBusyCursor()

    def _FileRevertMenu(self, event):
        year, month, day, id = self._GetEntryFormKeys()
        self._SetEntryModified(False)
        self._SetEntryFormDate(int(year), int(month), int(day), id)

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
        self.Bind(wx.EVT_BUTTON, _ChooseFontButton, id=self.choose_font_id)
        if self.options_dialog.ShowModal() != wx.ID_OK:
            self._SetFont(oldfont)

    def _FileQuitMenu(self, event):
        self.frame.Close()

    def _FileDiaryOptionsMenu(self, event):
        # Grab the controls
        author_name_box = self.frame.FindWindowById(self.author_name_id)
        author_global_radio = self.frame.FindWindowById(self.author_global_id)
        author_per_entry_radio = \
            self.frame.FindWindowById(self.author_per_entry_id)

        # Enable/disable the author name box
        def _ChooseAuthorGlobal(event2):
            author_name_box.Enable(True)
        self.Bind(wx.EVT_RADIOBUTTON, _ChooseAuthorGlobal,
                  id=self.author_global_id)

        def _ChooseAuthorPerEntry(event2):
            author_name_box.Enable(False)
        self.Bind(wx.EVT_RADIOBUTTON, _ChooseAuthorPerEntry,
                  id=self.author_per_entry_id)

        # Set the controls to the current settings
        author_name = self.entries.get_author_name()
        if author_name is None:
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
            self._UpdateAuthorBox()  # Show/Hide the author box as needed
            self._SetDiaryModified(True)

    def _EntryNewMenu(self, event):
        year, month, day, id = self._GetEntryFormKeys()
        new_id = self.entries.get_new_id(year, month, day)
        self._SetEntryFormDate(year, month, day, new_id)

    def _EntryNewTodayMenu(self, event):
        ts = time.localtime()
        new_id = self.entries.get_new_id(ts[0], ts[1], ts[2])
        self._SetEntryFormDate(ts[0], ts[1], ts[2], new_id)

    def _EntryDuplicateMenu(self, event):
        year, month, day, id = self._GetEntryFormKeys()
        self._DuplicateEntry(year, month, day, id)

    def _EntryRedateMenu(self, event):
        year, month, day, id = self._GetEntryFormKeys()
        self._RedateEntry(year, month, day, id)

    def _EntryDeleteMenu(self, event):
        year, month, day, id = self._GetEntryFormKeys()
        self._DeleteEntry(year, month, day, id)

    def _EntryPreviewMenu(self, event):
        try:
            datestr, subject, author, text = self._GetCurrentEntryPieces()
            if self.entries.get_author_global():
                author = self.entries.get_author_name()
            self.printer.PreviewText(self.datafile, subject, author,
                                     datestr, text)
        except Exception:
            raise

    def _EntryPrintMenu(self, event):
        try:
            datestr, subject, author, text = self._GetCurrentEntryPieces()
            if self.entries.get_author_global():
                author = self.entries.get_author_name()
            self.printer.Print(self.datafile, subject, author,
                               datestr, text)
        except Exception:
            pass

    def _HelpAboutMenu(self, event):
        wx.MessageBox((f'ThotKeeper - a personal daily journal application.\n'
                       f'\n'
                       f'Copyright (c) 2004-2020 C. Michael Pilato.  '
                       f'All rights reserved.\n'
                       f'\n'
                       f'ThotKeeper is open source software developed under '
                       f'the BSD License.  Question, comments, and code '
                       f'contributions are welcome.\n'
                       f'\n'
                       f'Website: http://www.thotkeeper.org/\n'
                       f'Version: {__version__}\n'),
                      'About ThotKeeper',
                      wx.OK | wx.CENTER,
                      self.frame)

    def _HelpUpdateMenu(self, event):
        new_version = None
        from .utils import (update_check, get_update_message)
        try:
            new_version, info_url = update_check()
        except Exception as e:
            wx.MessageBox((f'Error occurred while checking for updates\n'
                           f'{e}'),
                          'Update Check',
                          wx.OK | wx.ICON_ERROR,
                          self.frame)
            return
        wx.MessageBox(get_update_message(new_version, info_url),
                      'Update Check', wx.OK, self.frame)

    # -----------------------------------------------------------------
    # Miscellaneous Event Handlers
    # -----------------------------------------------------------------

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
        data = tree.GetItemData(item)
        if not data.day:
            event.Skip()
            return
        self._SetEntryFormDate(data.year, data.month, data.day, data.id)
