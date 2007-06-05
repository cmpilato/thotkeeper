#!/usr/bin/python
#
# ThotKeeper -- a personal daily journal application.
#
# Copyright (c) 2004-2006 C. Michael Pilato.  All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE file which can be found at the top level of the ThotKeeper
# distribution.
#
# Contact information:
#    C. Michael Pilato <cmpilato@red-bean.com>
#    http://www.cmichaelpilato.com/

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

class ThotKeeperEventTree(wxTreeCtrl):
    def OnCompareItems(self, item1, item2):
        data1 = self.GetItemData(item1).GetData()
        data2 = self.GetItemData(item2).GetData()
        if data1 is None or data2 is None:
            return 0
        if data1 == data2:
            return 0
        elif data1 > data2:
            return -1
        else:
            return 1
        
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
    
    def FindChild(self, id, data):
        cookie = None
        while 1:
            if cookie:
                child_id, cookie = self.GetNextChild(id, cookie)
            else:
                child_id, cookie = self.GetFirstChild(id)
            if not child_id.IsOk():
                break
            child_data = self.GetItemData(child_id).GetData()
            if child_data == data:
                return child_id
        return None
    
    def GetDateStack(self, year, month, day):
        stack = []
        id = self.GetRootItem()
        stack.append(id) # 0
        id = self.FindChild(id, [year, None, None])
        stack.append(id) # 1
        if id:
            id = self.FindChild(id, [year, month, None])
            stack.append(id) # 2
            if id:
                id = self.FindChild(id, [year, month, day])
                stack.append(id) # 3
            else:
                stack.append(None) # 3
        else:
            stack.append(None) # 2
            stack.append(None) # 3
        return stack
    
    def Prune(self, id):
        while 1:
            parent_id = self.GetItemParent(id)
            # Don't delete the root node.
            if not parent_id.IsOk():
                break        
            self.Delete(id)
            if self.GetChildrenCount(parent_id):
                break
            id = parent_id

    def EntryChangedListener(self, entry, year, month, day):
        """Callback for TKEntries.set_entry()."""
        wxBeginBusyCursor()
        stack = self.GetDateStack(year, month, day)
        if not entry:
            if stack[3]:
                self.Prune(stack[3])
        else:
            subject = entry.get_subject()
            if not stack[1]:
                stack[1] = self.AppendItem(stack[0],
                                           str(year),
                                           -1, -1,
                                           wxTreeItemData([year, None, None]))
                self.SortChildren(stack[0])
            if not stack[2]:
                stack[2] = self.AppendItem(stack[1],
                                           month_names[month - 1],
                                           -1, -1,
                                           wxTreeItemData([year, month, None]))
                self.SortChildren(stack[1])
            if not stack[3]:
                stack[3] = self.AppendItem(stack[2],
                                           "%02d - %s" % (int(day), subject),
                                           -1, -1,
                                           wxTreeItemData([year, month, day]))
                self.SortChildren(stack[2])
            else:
                self.SetItemText(stack[3], "%02d - %s" % (int(day), subject))
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

class ThotKeeperEventCal(wxCalendarCtrl):
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
        
    def EntryChangedListener(self, entry, year, month, day):
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

class ThotKeeperEntryPrinter(HtmlEasyPrinting):
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
        self.datafile = datafile
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
        self.printer = ThotKeeperEntryPrinter()
        
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
        self.cal = ThotKeeperEventCal(parent=self.panel,
                                      style=wxCAL_SEQUENTIAL_MONTH_SELECTION)
        self.tree = ThotKeeperEventTree(parent=self.panel,
                                        style=wxTR_HAS_BUTTONS)
        self.resources.AttachUnknownControl('TKCalendar',
                                            self.cal, self.panel)
        self.resources.AttachUnknownControl('TKDateTree',
                                            self.tree, self.panel)

        # Populate the tree widget.
        self.tree = self.frame.FindWindowById(self.datetree_id)
        self.tree_root = self.tree.AddRoot('ThotKeeper Entries', -1, -1,
                                           wxTreeItemData([None, None, None]))
        
        # Set the default font size for the diary entry text widget.
        font = wxFont(conf.font_size, wxDEFAULT, wxNORMAL, wxNORMAL,
                      false, conf.font_face)
        self._SetFont(font)
        
        # Event handlers.  They are the key to the world.
        EVT_CLOSE(self.frame, self._FrameClosure)
        EVT_BUTTON(self, self.today_id, self._TodayButtonActivated)
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
            
        # If we were not given a datafile, or the one we were given is
        # invalid, ask for a valid one.
        self._SetTitle()
        if self.datafile:
            self._SetDataFile(self.datafile)
        else:
            self._SetDataFile(conf.data_file)

        # Display our frame.
        self.frame.SetSize(conf.size)
        if conf.position is not None:
            self.frame.SetPosition(conf.position)
        else:
            self.frame.Center()
        self.frame.Show(true)

        # Tell wxWidgets that this is our main window
        self.SetTopWindow(self.frame)

        # Return a success flag
        return true

    def _SetFont(self, font):
        """Set the font used by the entry text field."""
        global conf
        self.frame.FindWindowById(self.text_id).SetFont(font)
        conf.font_face = font.GetFaceName()
        conf.font_size = font.GetPointSize()
        self.options_dialog.FindWindowById(self.font_id).SetLabel(
            "%s, %dpt" % (conf.font_face, conf.font_size))
    
    def _SetDataFile(self, datafile, create=false):
        """Set the active datafile, possible creating one on disk."""
        global conf
        self.parser = tk_data.TKDataParser()
        self.tree.DeleteChildren(self.tree_root)
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
                self.parser.unparse_data(datafile, None)
            self.frame.SetStatusText('Loading %s...' % datafile)
            self.entries = self.parser.parse_data(datafile)
            timestruct = time.localtime()
            years = self.entries.get_years()
            years.sort()
            years.reverse()
            for year in years:
                year_item = self.tree.AppendItem(
                    self.tree_root, str(year), -1, -1,
                    wxTreeItemData([year, None, None]))
                months = self.entries.get_months(year)
                months.sort()
                months.reverse()
                for month in months:
                    month_item = self.tree.AppendItem(
                        year_item, month_names[month - 1],
                        -1, -1, wxTreeItemData([year, month, None]))
                    days = self.entries.get_days(year, month)
                    days.sort()
                    days.reverse()
                    for day in days:
                        subject = self.entries.get_entry(
                            year, month, day).get_subject()
                        label = "%02d - %s" % (int(day), subject)
                        day_item = self.tree.AppendItem(
                            month_item, label, -1, -1,
                            wxTreeItemData([year, month, day]))
                    if year == timestruct[0] and month == timestruct[1]:
                        self.tree.Expand(month_item)
                    else:
                        self.tree.Collapse(month_item)
                if year == timestruct[0]:
                    self.tree.Expand(year_item)
                else:
                    self.tree.Collapse(year_item)
            self.tree.Expand(self.tree_root)
            self.entries.register_listener(self.tree.EntryChangedListener)
            self.entries.register_listener(self.cal.EntryChangedListener)
            self.datafile = datafile
            self._SetTitle()
            self.panel.Show(true)
            self._SetEntryFormDate(timestruct[0], timestruct[1], timestruct[2])
            self.cal.HighlightEvents(self.entries)

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
    
    def _SetEntryFormDate(self, year, month, day):
        """Set the data on the entry form."""
        if self._RefuseUnsavedModifications():
            return false
        self.date = "%d-%d-%d" % (year, month, day)
        date = wxDateTime()
        date.ParseFormat(self.date + " 11:59:59", '%Y-%m-%d %H:%M:%S', date)
        label = date.Format("%A, %B %d, %Y")
        self.frame.FindWindowById(self.date_id).SetLabel(label)
        text = subject = author = ''
        has_entry = 0
        entry = self.entries.get_entry(year, month, day)
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
    
    def _EntryDataChanged(self, event):
        self._SetModified(true)

    def _TreeActivated(self, event):
        item = event.GetItem()
        data = self.tree.GetItemData(item).GetData()
        if not data[2]:
            event.Skip()
            return
        self._SetEntryFormDate(data[0], data[1], data[2])

    def _GetEntryFormDate(self):
        pieces = self.date.split('-')
        return map(int, pieces)

    def _GetEntryFormBits(self):
        year, month, day = self._GetEntryFormDate()
        author = self.frame.FindWindowById(self.author_id).GetValue()
        subject = self.frame.FindWindowById(self.subject_id).GetValue()
        text = self.frame.FindWindowById(self.text_id).GetValue()
        return year, month, day, author, subject, text
        
    def _SaveEntriesToPath(self, path=None):
        if self.is_modified:
            year, month, day, author, subject, text = self._GetEntryFormBits()
            self.entries.set_entry(year, month, day, author, subject, text)
        if path is None:
            path = conf.data_file
        self.parser.unparse_data(path, self.entries)
        if path != conf.data_file:
            self._SetDataFile(path, false)
        self._SetModified(false)

    def _TreeEditMenu(self, event):
        item = self.tree.GetSelection()
        data = self.tree.GetItemData(item).GetData()
        if not data[2]:
            event.Skip()
            return
        self._SetEntryFormDate(data[0], data[1], data[2])

    def _TreeDeleteMenu(self, event):
        item = self.tree.GetSelection()
        data = self.tree.GetItemData(item).GetData()
        if not data[2]:
            wxMessageBox("This operation is not currently supported.",
                         "Confirm Deletion", wxOK | wxICON_ERROR, self.frame)
        elif wxOK == wxMessageBox(
            "Are you sure you want to delete the entry for " +
            "%s-%s-%s?" % (data[0], data[1], data[2]), "Confirm Deletion",
            wxOK | wxCANCEL | wxICON_QUESTION, self.frame):
            self.entries.remove_entry(data[0], data[1], data[2])
            self.parser.unparse_data(conf.data_file, self.entries)

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
            if not data[2]:
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
            wxYield()
            wxBeginBusyCursor()
            self._SetDataFile(path, true)
            wxEndBusyCursor()
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
            wxYield()
            wxBeginBusyCursor()
            self._SetDataFile(path, false)
            wxEndBusyCursor()
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
            wxYield()
            wxBeginBusyCursor()
            self._SaveEntriesToPath(path)
            wxEndBusyCursor()
        dialog.Destroy()

    def _FileRevertMenu(self, event):
        year, month, day = self._GetEntryFormDate()
        self._SetModified(false)
        self._SetEntryFormDate(int(year), int(month), int(day))

    def _GetCurrentEntryPieces(self):
        year, month, day, author, subject, text = self._GetEntryFormBits()
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
                wxYield()
                wxBeginBusyCursor()
                self._SetFont(font)
                wxEndBusyCursor()
            dialog.Destroy()
        EVT_BUTTON(self, self.choose_font_id, _ChooseFontButton)
        self.options_dialog.ShowModal()
        
    def _FileQuitMenu(self, event):
        self.frame.Destroy()
        
    def _HelpAboutMenu(self, event):
        wxMessageBox("ThotKeeper" +
                     " -- a personal daily journal application.\n\n" +
                     "Copyright (c) 2004-2006 C. Michael Pilato\n" +
                     "Email: cmpilato@red-bean.com\n" +
                     "Website: http://www.cmichaelpilato.com/\n" +
                     "All rights reserved.\n",
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
    
