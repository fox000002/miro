"""Handle selection."""

import app
import database
import eventloop
import folder
import guide
import item
import tabs
import playlist
import feed
import views
import template

def getID(obj):
    """Gets an ID to use for an object.  For tabs, this is the object ID that
    maps to the tab.  For other objects this is the actual DDBObject ID."""
    if isinstance(obj, tabs.Tab):
        return obj.objID()
    else:
        return obj.getID()

class SelectionArea(object):
    """Represents an area that holds a selection.  Currently we have 2
    SelectionAreas, the tab list and the item list.  SelectionAreas hold
    several database views, for instance the tab list contains
    views.guideTabs, views.staticTabs, views.feedTabs and views.playlistTabs.
    All the items selected in an area must be in a single view.

    Member variables:

    currentView -- The view that items are currently selected in, or None if
        there are no items selected.
    currentSelection -- set of object IDs that are currently selected.
    """

    def __init__(self, selectionHandler):
        self.currentSelection = set()
        self.currentView = None
        self.handler = selectionHandler

    def switchView(self, view):
        if self.currentView == view:
            return
        if self.currentView:
            self.clearSelection()
        self.currentView = view
        self.currentView.addRemoveCallback(self.onRemove)
        self.currentView.addAddCallback(self.onAdd)

    def selectItem(self, view, id):
        self.switchView(view)
        obj = view.getObjectByID(id)
        obj.setSelected(True)
        self.currentSelection.add(id)

    def deselectItem(self, view, id):
        if view != self.currentView:
            raise ValueError("view != current view in deselectItem()")
        obj = view.getObjectByID(id)
        obj.setSelected(False)
        self.currentSelection.remove(id)

    def toggleItemSelect(self, view, id):
        self.switchView(view)
        if id in self.currentSelection:
            self.deselectItem(view, id)
        else:
            self.selectItem(view, id)

    def clearSelection(self):
        """Clears the current selection."""

        for id in self.currentSelection:
            obj = self.currentView.getObjectByID(id)
            obj.setSelected(False)
        self.currentSelection = set()
        if self.currentView is not None:
            self.currentView.removeRemoveCallback(self.onRemove)
            self.currentView.removeAddCallback(self.onAdd)
            self.currentView = None

    def selectAll(self):
        """Select all objects in the current View."""
        
        view = self.currentView
        if view:
            for obj in view:
                if obj.getID not in self.currentSelection:
                    self.selectItem(view, obj.getID())


    def calcExtendRange(self, view, id):
        idIsBefore = False
        gotFirst = False
        firstID = lastID = None
        for obj in view:
            objID = getID(obj)
            if objID == id and not gotFirst:
                idIsBefore = True
            if objID in self.currentSelection:
                if not gotFirst:
                    firstID = objID
                    gotFirst = True
                lastID = objID
        if firstID is None or lastID is None:
            raise AssertionError("Couldn't find my selected IDs")
        if idIsBefore:
            return id, lastID
        else:
            return firstID, id

    def extendSelection(self, view, id):
        """Extends the selection in response to a shift-select.  If id is on
        top of the current selection, we will select everything between the id
        and the last selected item.  If id is below it or in the middle, we
        will select between the first selected item and id.  
        """

        self.switchView(view)
        if len(self.currentSelection) == 0:
            return self.selectItem(view, id)
        firstID, lastID = self.calcExtendRange(view, id)
        self.selectBetween(view, firstID, lastID)

    def selectBetween(self, view, firstID, lastID):
        """Select all items in view between firstID and lastID."""

        self.switchView(view)
        selecting = False
        for obj in view:
            id = getID(obj)
            if selecting and id not in self.currentSelection:
                self.selectItem(view, id)
            if id == firstID:
                selecting = True
                if id not in self.currentSelection:
                    self.selectItem(view, id)
            if id == lastID:
                break

    def onRemove(self, obj, id):
        if id in self.currentSelection:
            if obj.idExists():
                obj.setSelected(False)
            self.currentSelection.remove(id)

    def setObjectsActive(self, newValue):
        """Iterate through all selected objects and call setActive on them,
        passing in newValue.
        """

        for id in self.currentSelection:
            obj = self.currentView.getObjectByID(id)
            obj.setActive(newValue)

    def onAdd(self, obj, id):
        if obj.getSelected() and id not in self.currentSelection:
            # this happens when we remove/add the object to reorder it in a
            # playlist
            self.currentSelection.add(id)

    def getTypesDetailed(self):
        """Get the type of objects that are selected.  

        Returns a set, containing all the type of objects selected.  The
        members will be one of the following:

        'item', 'downloadeditem' 'playlisttab', playlistfoldertab,
        'channeltab', 'channelfoldertab', 'guidetab', 'addedguidetab',
        'statictab'.

        """

        types = set()
        for id in self.currentSelection:
            obj = self.currentView.getObjectByID(id)
            if isinstance(obj, item.Item):
                if obj.isDownloaded():
                    newType = 'downloadeditem'
                else:
                    newType = 'item'
            elif isinstance(obj, tabs.Tab):
                objClass = obj.obj.__class__
                if objClass == playlist.SavedPlaylist:
                    newType = 'playlisttab'
                elif objClass == folder.PlaylistFolder:
                    newType = 'playlistfoldertab'
                elif objClass == feed.Feed:
                    newType = 'channeltab'
                elif objClass == folder.ChannelFolder:
                    newType = 'channelfoldertab'
                elif objClass == guide.ChannelGuide:
                    if obj.obj.getDefault():
                        newType = 'guidetab'
                    else:
                        newType = 'addedguidetab'
                elif objClass == tabs.StaticTab:
                    newType = 'statictab'
                else:
                    raise ValueError("Bad selected tab type: %s" % obj.obj)
            else:
                raise ValueError("Bad selected object type: %s" % obj)
            types.add(newType)
        self.simplifyTypes(types) 
        # we don't care about the result of simplifyTypes, but the error
        # checking is useful
        return types

    def simplifyTypes(self, types):
        if len(types) == 0:
            return None
        elif types.issubset(set(["item", "downloadeditem"])):
                return "item"
        elif types.issubset(set(["playlistfoldertab", "playlisttab"])):
                return "playlisttab"
        elif types.issubset(set(["channelfoldertab", "channeltab"])):
                return "channeltab"
        elif len(types) == 1:
            for type in types:
                return type
        else:
            raise ValueError("Multiple types selected: %s" % types)

    def getType(self):
        """Get the simplified version of the type of objects that are
        selected.  getType() works like getTypesDetailed(), but it just
        returns one value.  It doesn't differentiate between playlists and
        playlist folders, and items and downloaded items for example.

        The return value will be one of

        "item", "playlisttab", "channeltab", 'guidetab', 'addedguidetab',
        'statictab', or None if nothing is selected.  

        """

        return self.simplifyTypes(self.getTypesDetailed())

    def getObjects(self):
        view = self.currentView
        return [view.getObjectByID(id) for id in self.currentSelection]

class TabSelectionArea(SelectionArea):
    """Selection area for the tablist.  This has a couple special cases to
    ensure that we always have at least one tab selected.
    """

    def toggleItemSelect(self, view, id):
        # Don't let a control select deselect the last selected item in the
        # tab list.
        if self.currentSelection == set([id]):
            return
        else:
            return SelectionArea.toggleItemSelect(self, view, id)

    def onRemove(self, obj, id):
        SelectionArea.onRemove(self, obj, id)
        # We may be removing/adding tabs quickly to reorder them.  Use an idle
        # callback to check if none are selected so we do the Right Thing in
        # this case.
        eventloop.addUrgentCall(self.checkNoTabsSelected,
                "checkNoTabsSelected")

    def checkNoTabsSelected(self):
        if len(self.currentSelection) == 0:
            prevTab = self.currentView.cur()
            if prevTab is None:
                # we remove the 1st tab in the list, try to select the new 1st
                # tab
                prevTab = self.currentView.getNext()
            if prevTab is None:
                # That was the last tab in the list, select the guide
                self.selectFirstGuide()
            else:
                self.selectItem(self.currentView, prevTab.objID())
            self.handler.displayCurrentTabContent()

    def selectFirstGuide(self):
        views.guideTabs.resetCursor()
        guide = views.guideTabs.getNext()
        self.selectItem(views.guideTabs, guide.objID())
        self.handler.displayCurrentTabContent()

    def isFolderSelected(self):
        """Returns if a channel/playlist folder is selected."""
        for tab in self.getObjects():
            if isinstance(tab.obj, folder.FolderBase):
                return True
        return False

class SelectionHandler(object):
    """Handles selection for Democracy.

    Attributes:

    tabListSelection -- SelectionArea for the tab list
    itemListSelection -- SelectionArea for the item list
    tabListActive -- does the tabListSelection the have the "active"
        selection?  In other words, is that the one that was clicked on last.
    """

    def __init__(self):
        self.tabListSelection = TabSelectionArea(self)
        self.itemListSelection = SelectionArea(self)
        self.lastDisplay = None
        self.tabListActive = True

    def getSelectionForArea(self, area):
        if area == 'tablist':
            return self.tabListSelection
        elif area == 'itemlist':
            return self.itemListSelection
        else:
            raise ValueError("Unknown area: %s" % area)

    def selectItem(self, area, view, id, shiftSelect, controlSelect):
        selection = self.getSelectionForArea(area)
        try:
            selectedObj = view.getObjectByID(id)
        except database.ObjectNotFoundError:
            # Item got deleted before the select went through.
            return

        # ignore control and shift when selecting static tabs
        if isinstance(selectedObj, tabs.Tab) and selectedObj.isStatic():
            controlSelect = shiftSelect = False

        if controlSelect:
            selection.toggleItemSelect(view, id)
        elif shiftSelect:
            selection.extendSelection(view, id)
        else:
            selection.clearSelection()
            selection.selectItem(view, id)

        if area == 'itemlist':
            self.setTabListActive(False)
            self.updateMenus()
        else:
            self.setTabListActive(True)
            self.displayCurrentTabContent()

    def setTabListActive(self, value):
        self.tabListActive = value
        self.tabListSelection.setObjectsActive(value)
        self.itemListSelection.setObjectsActive(not value)

    def calcSelection(self, area, sourceID):
        """Calculate the selection, given the ID of an object that was clicked
        on.  If sourceID is in the current selection, this will all the
        objects in the current selection, otherwise it will be only the object
        that corresponds to sourceID.  
        """

        selection = self.getSelectionForArea(area)
        if sourceID in selection.currentSelection:
            return set(selection.currentSelection)
        else:
            return set([sourceID])

    def selectFirstGuide(self):
        self.tabListSelection.selectFirstGuide()

    def selectTabByTemplateBase(self, tabTemplateBase):
        tabViews = [ 
            views.guideTabs, 
            views.staticTabs, 
            views.feedTabs, 
            views.playlistTabs,
        ]
        for view in tabViews:
            for tab in view:
                if tab.tabTemplateBase == tabTemplateBase:
                    self.selectItem('tablist', view, tab.objID(),
                            shiftSelect=False, controlSelect=False)
                    return

    def selectTabByObject(self, obj):
        channelTabOrder = app.getSingletonDDBObject(views.channelTabOrder)
        playlistTabOrder = app.getSingletonDDBObject(views.playlistTabOrder)
        tabViews = [ 
            views.guideTabs, 
            views.staticTabs, 
            channelTabOrder.getView(), 
            playlistTabOrder.getView(), 
        ]
        for view in tabViews:
            for tab in view:
                if tab.obj is obj:
                    self.selectItem('tablist', view, tab.objID(),
                            shiftSelect=False, controlSelect=False)
                    return

    def _chooseDisplayForCurrentTab(self):
        tls = self.tabListSelection
        frame = app.controller.frame

        if len(tls.currentSelection) == 0:
            raise AssertionError("No tabs selected")
        elif len(tls.currentSelection) == 1:
            for id in tls.currentSelection:
                tab = tls.currentView.getObjectByID(id)
                return app.TemplateDisplay(tab.contentsTemplate, 
                        frameHint=frame, areaHint=frame.mainDisplay, 
                        id=tab.obj.getID())
        else:
            foldersSelected = False
            type = tls.getType()
            if type == 'playlisttab':
                templateName = 'multi-playlist'
            elif type == 'channeltab':
                templateName = 'multi-channel'
            selectedChildren = 0
            selectedFolders = 0
            containedChildren = 0
            for tab in self.getSelectedTabs():
                if isinstance(tab.obj, folder.FolderBase):
                    selectedFolders += 1
                    view = tab.obj.getChildrenView()
                    containedChildren += view.len()
                    for child in view:
                        if child.getID() in tls.currentSelection:
                            selectedChildren -= 1
                else:
                    selectedChildren += 1
            return app.TemplateDisplay(templateName, frameHint=frame,
                    areaHint=frame.mainDisplay,
                    selectedFolders=selectedFolders,
                    selectedChildren=selectedChildren,
                    containedChildren=containedChildren)

    def updateMenus(self):
        from frontend import UIStrings
        tabTypes = self.tabListSelection.getTypesDetailed()
        if tabTypes.issubset(set(['guidetab', 'addedguidetab'])):
            guideURL = self.getSelectedTabs()[0].obj.getURL()
        else:
            guideURL = None
        multiple = len(self.tabListSelection.currentSelection) > 1

        actionGroups = {}
        strings = {}

        is_playlistlike = tabTypes.issubset (set(['playlisttab', 'playlistfoldertab']))
        is_channellike = tabTypes.issubset (set(['channeltab', 'channelfoldertab', 'addedguidetab']))
        is_channel = tabTypes.issubset (set(['channeltab', 'channelfoldertab']))
        strings["channel_remove"] = UIStrings.REMOVE
        strings["channel_rename"] = UIStrings.RENAME
        strings["channel_update"] = UIStrings.UPDATE_CHANNEL
        strings["playlist_remove"] = UIStrings.REMOVE
        strings["playlist_rename"] = UIStrings.RENAME
        strings["video_remove"] = UIStrings.REMOVE_VIDEO
        if len (tabTypes) == 1:
            if multiple:
                if 'playlisttab' in tabTypes:
                    strings["playlist_remove"] = UIStrings.REMOVE_PLAYLISTS
                elif 'playlistfoldertab' in tabTypes:
                    strings["playlist_remove"] = UIStrings.REMOVE_PLAYLIST_FOLDERS
                elif 'channeltab' in tabTypes:
                    strings["channel_remove"] = UIStrings.REMOVE_CHANNELS
                elif 'channelfoldertab' in tabTypes:
                    strings["channel_remove"] = UIStrings.REMOVE_CHANNEL_FOLDERS
                elif 'addedguidetab' in tabTypes:
                    strings["channel_remove"] = UIStrings.REMOVE_CHANNEL_GUIDES
            else:
                if 'playlisttab' in tabTypes:
                    strings["playlist_remove"] = UIStrings.REMOVE_PLAYLIST
                    strings["playlist_rename"] = UIStrings.RENAME_PLAYLIST
                elif 'playlistfoldertab' in tabTypes:
                    strings["playlist_remove"] = UIStrings.REMOVE_PLAYLIST_FOLDER
                    strings["playlist_rename"] = UIStrings.RENAME_PLAYLIST_FOLDER
                elif 'channeltab' in tabTypes:
                    strings["channel_remove"] = UIStrings.REMOVE_CHANNEL
                    strings["channel_rename"] = UIStrings.RENAME_CHANNEL
                elif 'channelfoldertab' in tabTypes:
                    strings["channel_remove"] = UIStrings.REMOVE_CHANNEL_FOLDER
                    strings["channel_rename"] = UIStrings.RENAME_CHANNEL_FOLDER
                elif 'addedguidetab' in tabTypes:
                    strings["channel_remove"] = UIStrings.REMOVE_CHANNEL_GUIDE
                    strings["channel_rename"] = UIStrings.RENAME_CHANNEL_GUIDE

        if multiple and is_channel:
            strings["channel_update"] = UIStrings.UPDATE_CHANNELS

        actionGroups["ChannelLikeSelected"] = is_channellike and not multiple
        actionGroups["ChannelLikesSelected"] = is_channellike
        actionGroups["PlaylistLikeSelected"] = is_playlistlike and not multiple
        actionGroups["PlaylistLikesSelected"] = is_playlistlike
        actionGroups["ChannelSelected"] = tabTypes.issubset (set(['channeltab'])) and not multiple
        actionGroups["ChannelsSelected"] = tabTypes.issubset (set(['channeltab', 'channelfoldertab']))
        actionGroups["ChannelFolderSelected"] = tabTypes.issubset(set(['channelfoldertab'])) and not multiple

        # Handle video item area.
        actionGroups["VideoSelected"] = False
        actionGroups["VideosSelected"] = False
        actionGroups["VideoPlayable"] = False
        if 'downloadeditem' in self.itemListSelection.getTypesDetailed():
            actionGroups["VideosSelected"] = True
            actionGroups["VideoPlayable"] = True
            if len(self.itemListSelection.currentSelection) == 1:
                actionGroups["VideoSelected"] = True
            else:
                strings["video_remove"] = UIStrings.REMOVE_VIDEOS
#        if len(self.itemListSelection.currentSelection) == 0:
#            if playable_videos:
#                actionGroups["VideoPlayable"] = True

        app.controller.frame.onSelectedTabChange(strings, actionGroups, guideURL)

    def displayCurrentTabContent(self):
        newDisplay = self._chooseDisplayForCurrentTab()
        # Don't redisplay the current tab if it's being displayed.  It messes
        # up our database callbacks.  The one exception is the guide tab,
        # where redisplaying it will reopen the home page.
        frame = app.controller.frame
        mainDisplay = frame.getDisplay(frame.mainDisplay) 
        if (self.lastDisplay and newDisplay == self.lastDisplay and
                self.lastDisplay is mainDisplay and
                newDisplay.templateName != 'guide'):
            return

        self.itemListSelection.clearSelection()
        self.updateMenus()
        # do a queueSelectDisplay to make sure that the selectDisplay gets
        # executed after our changes to the tablist template.  This makes tab
        # selection feel faster because the selection changes quickly.
        template.queueSelectDisplay(frame, newDisplay, frame.mainDisplay)
        self.lastDisplay = newDisplay

    def isTabSelected(self, tab):
        return tab.objID() in self.tabListSelection.currentSelection

    def getSelectedTabs(self):
        """Return a list of the currently selected Tabs. """

        return self.tabListSelection.getObjects()

    def getSelectedItems(self):
        """Return a list of the currently selected items. """

        return self.itemListSelection.getObjects()
