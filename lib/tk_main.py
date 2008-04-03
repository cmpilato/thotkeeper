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
from wxPython.wx import *
from wxPython.calendar import *
from wxPython.xrc import *
from wx.html import HtmlEasyPrinting

__version__ = "0.2-dev"

# Placeholder for the configuration class.
conf = None

month_names = ['January', 'February', 'March', 'April', 
               'May', 'June', 'July', 'August', 
               'September', 'October', 'November', 'December']

CONF_GROUP = 'options'
CONF_FONT_NAME = CONF_GROUP + '/font-face'
CONF_FONT_SIZE = CONF_GROUP + '/font-size'
CONF_DATA_FILE = CONF_GROUP + '/data-file'
CONF_POSITION = CONF_GROUP + '/window-position'
CONF_SIZE = CONF_GROUP + '/window-size'


########################################################################
###
###  CONFIGURATION ROUTINES
###

def AbsorbConf():
    global conf
    conf = wxConfig(style = wxCONFIG_USE_LOCAL_FILE)
    conf.font_face = conf.Read(CONF_FONT_NAME, 'Comic Sans MS')
    conf.font_size = conf.ReadInt(CONF_FONT_SIZE, 16)
    conf.data_file = conf.position = None
    if conf.Exists(CONF_DATA_FILE):
        conf.data_file = conf.Read(CONF_DATA_FILE)
    if conf.Exists(CONF_POSITION):
        position = conf.Read(CONF_POSITION).split(',')
        conf.position = wxPoint(int(position[0]), int(position[1]))
    size = conf.Read(CONF_SIZE, '600,400').split(',')
    conf.size = wxSize(int(size[0]), int(size[1]))

def FlushConf():
    global conf
    wc = wxConfigBase_Get()
    if conf.data_file:
        wc.Write(CONF_DATA_FILE, conf.data_file)
    wc.Write(CONF_FONT_NAME, conf.font_face)
    wc.WriteInt(CONF_FONT_SIZE, conf.font_size)
    if conf.position:
        wc.Write(CONF_POSITION, "%d,%d" %
                 (conf.position.x, conf.position.y))
    if conf.size:
        wc.Write(CONF_SIZE, "%d,%d" %
                 (conf.size.GetWidth(), conf.size.GetHeight()))
    wc.Flush()


########################################################################
###    
###  EVENT TREE SUBCLASS
###

class TKEntryKey:
    def __init__(self, year, month, day, id):
        self.year = year
        self.month = month
        self.day = day
        self.id = id

    def __cmp__(self, other):
        return cmp([self.year, self.month, self.day, self.id],
                   [other.year, other.month, other.day, other.id])

class TKEventTree(wxTreeCtrl):
    def __init__(self, parent, style):
        wxTreeCtrl.__init__(self, parent=parent, style=style)
        root_data = wxTreeItemData(TKEntryKey(None, None, None, None))
        self.root_id = self.AddRoot('ThotKeeper Entries', -1, -1, root_data)

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
        self.CollapseAllChildren(self.root_id)
        self.Expand(self.root_id)
        
    def EntryChangedListener(self, entry, year, month, day, id, expand=True):
        """Callback for TKEntries.store_entry()."""
        wxBeginBusyCursor()
        stack = self.GetDateStack(year, month, day, id)
        if not entry:
            if stack[3]:
                self.Prune(stack[3])
        else:
            subject = entry.get_subject()
            if not stack[1]:
                data = wxTreeItemData(TKEntryKey(year, None, None, None))
                stack[1] = self.AppendItem(stack[0],
                                           str(year),
                                           -1, -1, data)
                self.SortChildren(stack[0])
            if not stack[2]:
                data = wxTreeItemData(TKEntryKey(year, month, None, None))
                stack[2] = self.AppendItem(stack[1],
                                           month_names[month - 1],
                                           -1, -1, data)
                self.SortChildren(stack[1])
            if not stack[3]:
                data = wxTreeItemData(TKEntryKey(year, month, day, id))
                stack[3] = self.AppendItem(stack[2],
                                           "%02d - %s" % (int(day), subject),
                                           -1, -1, data)
                self.SortChildren(stack[2])
            else:
                self.SetItemText(stack[3], "%02d - %s" % (int(day), subject))
            if expand:
                self.Expand(stack[0])
                self.Expand(stack[1])
                self.Expand(stack[2])
                self.Expand(stack[3])
            self.SelectItem(stack[3])
        wxEndBusyCursor()


########################################################################
###
###  EVENT CALENDAR SUBCLASS
###

class TKEventCal(wxCalendarCtrl):
    def SetDayAttr(self, day, has_event):
        if has_event:
            attr = wxCalendarDateAttr()
            attr.SetTextColour(wxRED)
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
        wxBeginBusyCursor()
        for day in range(1, 32):
            if day in days and has_events:
                self.SetDayAttr(day, True)
            else:
                self.SetDayAttr(day, False)
        self.Refresh(true)
        wxEndBusyCursor()
        
    def EntryChangedListener(self, entry, year, month, day, id):
        """Callback for TKEntries.store_entry()."""
        date = self.GetDate()
        if date.GetYear() != year:
            return
        if (date.GetMonth() + 1) != month:
            return
        wxBeginBusyCursor()
        if entry:
            self.SetDayAttr(day, True)
        else:
            self.SetDayAttr(day, False)
        wxEndBusyCursor()


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

class ThotKeeper(wxApp):
    def __init__(self, datafile=None):
        self.cmd_datafile = datafile
        self.datafile = None
        wxApp.__init__(self)

    def OnInit(self):
        """wxWidgets calls this method to initialize the application"""
        global conf

        # Who am I?
        self.SetVendorName("Red-Bean Software")
        self.SetAppName("ThotKeeper")

        # Get our persisted options into an easily addressable object.
        AbsorbConf()

        # Get the XML Resource class
        resource_path = os.path.join(os.path.dirname(sys.argv[0]),
                                     'lib', 'tk_resources.xrc')
        self.resources = wxXmlResource(resource_path)
        self.calendar_id = self.resources.GetXRCID('TKCalendar')
        self.panel_id = self.resources.GetXRCID('TKPanel')
        self.datetree_id = self.resources.GetXRCID('TKDateTree')
        self.today_id = self.resources.GetXRCID('TKToday')
        self.next_id = self.resources.GetXRCID('TKNext')
        self.prev_id = self.resources.GetXRCID('TKPrev')
        self.date_id = self.resources.GetXRCID('TKEntryDate')
        self.author_id = self.resources.GetXRCID('TKEntryAuthor')
        self.subject_id = self.resources.GetXRCID('TKEntrySubject')
        self.text_id = self.resources.GetXRCID('TKEntryText')
        self.file_new_id = self.resources.GetXRCID('TKMenuFileNew')
        self.file_open_id = self.resources.GetXRCID('TKMenuFileOpen')
        self.file_save_id = self.resources.GetXRCID('TKMenuFileSave')
        self.file_saveas_id = self.resources.GetXRCID('TKMenuFileSaveAs')
        self.file_revert_id = self.resources.GetXRCID('TKMenuFileRevert')
        self.file_preview_id = self.resources.GetXRCID('TKMenuFilePreview')
        self.file_print_id = self.resources.GetXRCID('TKMenuFilePrint')
        self.file_quit_id = self.resources.GetXRCID('TKMenuFileQuit')
        self.help_about_id = self.resources.GetXRCID('TKMenuHelpAbout')
        self.open_tool_id = self.resources.GetXRCID('TKToolOpen')
        self.file_options_id = self.resources.GetXRCID('TKMenuFileOptions')
        self.choose_font_id = self.resources.GetXRCID('TKChooseFontButton')
        self.font_id = self.resources.GetXRCID('TKFontName')
        self.tree_edit_id = self.resources.GetXRCID('TKTreeMenuEdit')
        self.tree_delete_id = self.resources.GetXRCID('TKTreeMenuDelete')
        self.tree_expand_id = self.resources.GetXRCID('TKTreeMenuExpand')
        self.tree_collapse_id = self.resources.GetXRCID('TKTreeMenuCollapse')

        # Construct our datafile parser and placeholder for data.
        self.parser = None
        self.entries = None

        # Setup a printer object.
        self.printer = TKEntryPrinter()
        
        # Note that our input file is not modified.
        self.is_modified = false
        
        # Fetch our main frame.
        self.frame = self.resources.LoadFrame(None, 'TKFrame')

        # Fetch our main panel.
        self.panel = self.frame.FindWindowById(self.panel_id)
        self.panel.Show(false)

        # fetch our options dialog.
        self.options_dialog = self.resources.LoadDialog(self.frame,
                                                        'TKOptions')

        # Fetch (and assign) our menu bar.
        self.menubar = self.resources.LoadMenuBar('TKMenuBar')
        self.frame.SetMenuBar(self.menubar)

        # Create a status bar.import locale
        self.statusbar = self.frame.CreateStatusBar(2)
        self.statusbar.SetStatusWidths([-1, 100])
        
        # Replace "unknown" XRC placeholders with custom widgets.
        self.cal = TKEventCal(parent=self.panel,
                              style=wxCAL_SEQUENTIAL_MONTH_SELECTION)
        self.resources.AttachUnknownControl('TKCalendar',
                                            self.cal, self.panel)
        tree = TKEventTree(parent=self.panel,
                           style=wxTR_HAS_BUTTONS)
        self.resources.AttachUnknownControl('TKDateTree',
                                            tree, self.panel)

        # Populate the tree widget.
        self.tree = self.frame.FindWindowById(self.datetree_id)
        self.tree_root = self.tree.GetRootId()
        
        # Set the default font size for the diary entry text widget.
        self._SetFont(wxFont(conf.font_size, wxDEFAULT, wxNORMAL, wxNORMAL,
                             false, conf.font_face))
        
        # Event handlers.  They are the key to the world.
        EVT_CLOSE(self.frame, self._FrameClosure)
        EVT_BUTTON(self, self.today_id, self._TodayButtonActivated)
        EVT_BUTTON(self, self.next_id, self._NextButtonActivated)
        EVT_BUTTON(self, self.prev_id, self._PrevButtonActivated)
        EVT_TEXT(self, self.text_id, self._EntryDataChanged)
        EVT_TEXT(self, self.author_id, self._EntryDataChanged)
        EVT_TEXT(self, self.subject_id, self._EntryDataChanged)
        EVT_CALENDAR(self, self.calendar_id, self._CalendarChanged)
        EVT_CALENDAR_YEAR(self, self.calendar_id, self._CalendarDisplayChanged)
        EVT_CALENDAR_MONTH(self, self.calendar_id, self._CalendarDisplayChanged)
        EVT_MENU(self, self.file_new_id, self._FileNewMenu)
        EVT_MENU(self, self.file_open_id, self._FileOpenMenu)
        EVT_MENU(self, self.file_save_id, self._FileSaveMenu)
        EVT_MENU(self, self.file_saveas_id, self._FileSaveAsMenu)
        EVT_MENU(self, self.file_revert_id, self._FileRevertMenu)
        EVT_MENU(self, self.file_preview_id, self._FilePreviewMenu)
        EVT_MENU(self, self.file_print_id, self._FilePrintMenu)
        EVT_MENU(self, self.file_quit_id, self._FileQuitMenu)
        EVT_MENU(self, self.help_about_id, self._HelpAboutMenu)
        EVT_MENU(self, self.file_options_id, self._FileOptionsMenu)

        # Event handlers for the Tree widget.
        EVT_TREE_ITEM_ACTIVATED(self, self.datetree_id, self._TreeActivated)
        EVT_RIGHT_DOWN(self.tree, self._TreePopup)
        EVT_MENU(self.tree, self.tree_edit_id, self._TreeEditMenu)
        EVT_MENU(self.tree, self.tree_delete_id, self._TreeDeleteMenu)
        EVT_MENU(self.tree, self.tree_expand_id, self._TreeExpandMenu)
        EVT_MENU(self.tree, self.tree_collapse_id, self._TreeCollapseMenu)

        # Size and position our frame.
        self.frame.SetSize(conf.size)
        if conf.position is not None:
            self.frame.SetPosition(conf.position)
        else:
            self.frame.Center()

        # Init the frame with no datafile.
        old_conf_data_file = conf.data_file
        self._SetDataFile(None)

        # Now, show the frame.
        self.frame.Show(true)

        # If we were not given a datafile, or the one we were given is
        # invalid, ask for a valid one.
        if self.cmd_datafile or old_conf_data_file:
            self._SetDataFile(self.cmd_datafile or old_conf_data_file)

        # Tell wxWidgets that this is our main window
        self.SetTopWindow(self.frame)
        
        # Return a success flag
        return true

    def _SetFont(self, font):
        """Set the font used by the entry text field."""
        global conf
        wxBeginBusyCursor()
        self.frame.FindWindowById(self.text_id).SetFont(font)
        conf.font_face = font.GetFaceName()
        conf.font_size = font.GetPointSize()
        self.options_dialog.FindWindowById(self.font_id).SetLabel(
            "%s, %dpt" % (conf.font_face, conf.font_size))
        wxEndBusyCursor()
    
    def _SetDataFile(self, datafile, create=false):
        """Set the active datafile, possible creating one on disk."""
        global conf
        wxYield()
        wxBeginBusyCursor()
        try:
            self.parser = tk_data.TKDataParser()
            self.tree.PruneAll()
            self._SetModified(false)
            self.panel.Show(false)
            conf.data_file = datafile
            if datafile:
                datafile = os.path.abspath(datafile)
                if not os.path.exists(datafile) and not create:
                    wxMessageBox("Unable to find datafile '%s'." %
                                 (datafile),
                                 "Datafile Missing", wxOK | wxICON_ERROR,
                                 self.frame)
                    return
                elif create:
                    if os.path.exists(datafile):
                        os.remove(datafile)
                    self._SaveData(datafile, None)
                self.frame.SetStatusText('Loading %s...' % datafile)
                try:
                    self.entries = self.parser.parse_data(datafile)
                except tk_data.TKDataVersionException, e:
                    wxMessageBox("Datafile format used by '%s' is not "
                                 "supported ." % (datafile),
                                 "Datafile Version Error",
                                 wxOK | wxICON_ERROR,
                                 self.frame)
                    return
                timestruct = time.localtime()
    
                def _AddEntryToTree(entry):
                    year, month, day = entry.get_date()
                    id = entry.get_id()
                    self.tree.EntryChangedListener(entry, year, month,
                                                   day, id, False)
                self.entries.enumerate_entries(_AddEntryToTree)
                self.tree.CollapseTree()
                stack = filter(None, self.tree.GetDateStack(timestruct[0],
                                                            timestruct[1],
                                                            timestruct[2],
                                                            None))
                for item in stack:
                    self.tree.Expand(item)
                self.entries.register_listener(self.tree.EntryChangedListener)
                self.entries.register_listener(self.cal.EntryChangedListener)
                self._SetEntryFormDate(timestruct[0], timestruct[1], timestruct[2])
                self.cal.HighlightEvents(self.entries)
                self.panel.Show(true)
                self.frame.Layout()
            self.datafile = datafile
            self._SetTitle()
        finally:
            wxEndBusyCursor()

    def _SaveData(self, path, entries):
        self.parser.unparse_data(path, entries)
        
    def _SetTitle(self):
        title = "ThotKeeper%s%s" \
                % (self.datafile and " - " + self.datafile or "",
                   self.is_modified and " [modified]" or "")
        self.frame.SetTitle(title)
        
    def _RefuseUnsavedModifications(self):
        """If there exist unsaved entry modifications, inform the user
        and return true.  Otherwise, return false."""
        if self.is_modified:
            wxMessageBox("Entry has been modified.  You must " +
                         "either save or revert it.", "Modified Entry",
                         wxOK | wxICON_INFORMATION, self.frame)
            return true
        return false

    ### FIXME: This function needs a new name
    def _SetEntryFormDate(self, year, month, day, id=-1):
        """Set the data on the entry form."""
        if self._RefuseUnsavedModifications():
            return false
        firstid = self.entries.get_first_id(year, month, day)
        if id == -1:
            id = firstid
        self.entry_form_keys = [year, month, day, id]
        date = wxDateTime()
        date.ParseFormat("%d-%d-%d 11:59:59" % (year, month, day),
                         '%Y-%m-%d %H:%M:%S', date)
        label = date.Format("%A, %B %d, %Y")
        if firstid is not None and (id is None or id>firstid):
            label += " (" + repr(self.entries.get_id_pos(year, month, day, id)+1) + ")"
            self.frame.FindWindowById(self.prev_id).Enable(true)
        else:
            self.frame.FindWindowById(self.prev_id).Enable(false)
        if id is not None:
            self.frame.FindWindowById(self.next_id).Enable(true)
        else:
            self.frame.FindWindowById(self.next_id).Enable(false)
        self.frame.FindWindowById(self.date_id).SetLabel(label)
        text = subject = author = ''
        has_entry = 0
        entry = self.entries.get_entry(year, month, day, id)
        if entry is not None:
            text = entry.get_text()
            author = entry.get_author()
            subject = entry.get_subject()
        self.frame.FindWindowById(self.author_id).SetValue(author)
        self.frame.FindWindowById(self.subject_id).SetValue(subject)
        self.frame.FindWindowById(self.text_id).SetValue(text)
        self._TogglePrintMenus(entry and true or false)
        self._SetModified(false)
        
    def _TogglePrintMenus(self, enable=true):
        self.menubar.FindItemById(self.file_print_id).Enable(enable)
        self.menubar.FindItemById(self.file_preview_id).Enable(enable)
        
    def _SetModified(self, enable=true):
        self.is_modified = enable
        self.menubar.FindItemById(self.file_save_id).Enable(enable)
        self.menubar.FindItemById(self.file_revert_id).Enable(enable)
        if self.is_modified:
            self._TogglePrintMenus(true)
        self._SetTitle()

    def _FrameClosure(self, event):
        self.frame.SetStatusText("Quitting...")
        conf.size = self.frame.GetSize()
        conf.position = self.frame.GetPosition()
        if event.CanVeto() and self._RefuseUnsavedModifications():
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
        wxBeginBusyCursor()
        for day in range(1, 32):
            if day in days and has_events:
                self.cal.SetDayAttr(day, True)
            else:
                self.cal.SetDayAttr(day, False)
        self.cal.Refresh(true)
        wxEndBusyCursor()
        
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
        self._SetModified(true)

    def _TreeActivated(self, event):
        item = event.GetItem()
        data = self.tree.GetItemData(item).GetData()
        if not data.day:
            event.Skip()
            return
        self._SetEntryFormDate(data.year, data.month, data.day, data.id)

    def _GetEntryFormKeys(self):
        ### FIXME: This interface is ... hacky.
        return self.entry_form_keys[0], self.entry_form_keys[1], \
               self.entry_form_keys[2], self.entry_form_keys[3]

    def _GetEntryFormBits(self):
        year, month, day, id = self._GetEntryFormKeys()
        author = self.frame.FindWindowById(self.author_id).GetValue()
        subject = self.frame.FindWindowById(self.subject_id).GetValue()
        text = self.frame.FindWindowById(self.text_id).GetValue()
        return year, month, day, author, subject, text, id
        
    def _SaveEntriesToPath(self, path=None):
        wxYield()
        wxBeginBusyCursor()
        if self.is_modified:
            year, month, day, author, subject, text, id \
                  = self._GetEntryFormBits()
            if id is None:
                id = self.entries.get_last_id(year, month, day)
                if id is None:
                    id = 1
                else:
                    id = id + 1
            self.entries.store_entry(tk_data.TKEntry(author, subject, text,
                                                     year, month, day, id))
        if path is None:
            path = conf.data_file
        self._SaveData(path, self.entries)
        if path != conf.data_file:
            self._SetDataFile(path, false) 
        self._SetModified(false)
        self.frame.FindWindowById(self.next_id).Enable(true)
        wxEndBusyCursor()

    def _TreeEditMenu(self, event):
        item = self.tree.GetSelection()
        data = self.tree.GetItemData(item).GetData()
        if not data.day:
            event.Skip()
            return
        self._SetEntryFormDate(data.year, data.month, data.day, data.id)

    def _TreeDeleteMenu(self, event):
        item = self.tree.GetSelection()
        data = self.tree.GetItemData(item).GetData()
        position = self.entries.get_id_pos(data.year, data.month,
                                           data.day, data.id) + 1
        if not data.day:
            wxMessageBox("This operation is not currently supported.",
                         "Confirm Deletion", wxOK | wxICON_ERROR, self.frame)
        elif wxOK == wxMessageBox(
            "Are you sure you want to delete the entry for " +
            "%s-%s-%s (%s)?" % (data.year, data.month, data.day, position),
            "Confirm Deletion",
            wxOK | wxCANCEL | wxICON_QUESTION, self.frame):
            self.entries.remove_entry(data.year, data.month,
                                      data.day, data.id)
            self._SaveData(conf.data_file, self.entries)

    def _TreeExpandMenu(self, event):
        def _ExpandCallback(id):
            self.tree.Expand(id)
        self.tree.Walker(_ExpandCallback)

    def _TreeCollapseMenu(self, event):
        def _CollapseCallback(id):
            self.tree.Collapse(id)
        self.tree.Walker(_CollapseCallback)

    def _TreePopup(self, event):
        item, flags = self.tree.HitTest(event.GetPosition())
        popup = self.resources.LoadMenu('TKTreePopup')
        if item and flags & (wxTREE_HITTEST_ONITEMBUTTON
                             | wxTREE_HITTEST_ONITEMICON
                             | wxTREE_HITTEST_ONITEMINDENT
                             | wxTREE_HITTEST_ONITEMLABEL
                             | wxTREE_HITTEST_ONITEMRIGHT
                             | wxTREE_HITTEST_ONITEMSTATEICON):
            if not self.tree.IsSelected(item):
                self.tree.SelectItem(item)
            data = self.tree.GetItemData(item).GetData()
            if not data.day:
                popup.Enable(self.tree_edit_id, false)
        else:
            popup.Enable(self.tree_edit_id, false)
            popup.Enable(self.tree_delete_id, false)
        self.tree.PopupMenu(popup)

    def _FileNewMenu(self, event):
        global conf
        directory = '.'
        if os.environ.has_key('HOME'):
            directory = os.environ['HOME']
        if conf.data_file is not None:
            directory = os.path.dirname(conf.data_file)
        dialog = wxFileDialog(self.frame, "Create new data file", directory,
                              '', '*.xml', wxSAVE | wxOVERWRITE_PROMPT)
        if dialog.ShowModal() == wxID_OK:
            path = dialog.GetPath()
            self._SetDataFile(path, true)
        dialog.Destroy()
        
    def _FileOpenMenu(self, event):
        global conf
        directory = '.'
        if os.environ.has_key('HOME'):
            directory = os.environ['HOME']
        if conf.data_file is not None:
            directory = os.path.dirname(conf.data_file)
        dialog = wxFileDialog(self.frame, "Open existing data file",
                              directory, '', '*.xml', wxOPEN)
        if dialog.ShowModal() == wxID_OK:
            path = dialog.GetPath()
            self._SetDataFile(path, false)
        dialog.Destroy()

    def _FileSaveMenu(self, event):
        self._SaveEntriesToPath(None)
        
    def _FileSaveAsMenu(self, event):
        global conf
        directory = os.path.dirname(conf.data_file)
        dialog = wxFileDialog(self.frame, "Save as a new data file", directory,
                              '', '*.xml', wxSAVE | wxOVERWRITE_PROMPT)
        if dialog.ShowModal() == wxID_OK:
            path = dialog.GetPath()
            self._SaveEntriesToPath(path)
        dialog.Destroy()

    def _FileRevertMenu(self, event):
        year, month, day, id = self._GetEntryFormKeys()
        self._SetModified(false)
        self._SetEntryFormDate(int(year), int(month), int(day), id)

    def _GetCurrentEntryPieces(self):
        year, month, day, author, subject, text, id = self._GetEntryFormBits()
        date = wxDateTime()
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
        def _ChooseFontButton(event2):
            text = self.frame.FindWindowById(self.text_id)
            font_data = wxFontData()
            font_data.SetInitialFont(text.GetFont())
            dialog = wxFontDialog(self.options_dialog, font_data)
            if dialog.ShowModal() == wxID_OK:
                font = dialog.GetFontData().GetChosenFont()
                self._SetFont(font)
            dialog.Destroy()
        EVT_BUTTON(self, self.choose_font_id, _ChooseFontButton)
        self.options_dialog.ShowModal()
        
    def _FileQuitMenu(self, event):
        self.frame.Destroy()
        
    def _HelpAboutMenu(self, event):
        wxMessageBox("ThotKeeper, version %s\n"
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
                     wxOK | wxCENTER, self.frame)

    def OnExit(self):
        FlushConf()


def main():
    file = None
    argc = len(sys.argv)
    if argc > 1:
        file = sys.argv[1]
    tk = ThotKeeper(file)
    tk.MainLoop()
    tk.OnExit()
    global conf
    del conf
    
