# -*- coding: UTF-8 -*-
##
##    Copyright (C) 2007 Rob Wallace rob[at]wallace(dot)gen(dot)nz
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published
## by the Free Software Foundation; version 2 only.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
import os
#====
import pygtk
pygtk.require('2.0')
#====

import gtk
from jbrout.commongtk import PictureSelector

from libs.gladeapp import GladeApp
try:
    import pyexiv2
    pyexiv2Avaliable = True
except:
    print "pyexiv2 not avaliable trying exif"
    from libs import exif
    pyexiv2Avaliable = False

import re

class WinViewExif(GladeApp):
    glade=os.path.join(os.path.dirname(__file__), 'viewExif.glade')

    #-- WinViewExif.new {
    def init(self, nodes):
        #############################################################
        ## IN in self.nodes:
        ##  - a list of PhotoNodes()
        #############################################################
        self.main_widget.set_modal(True)
        self.main_widget.set_position(gtk.WIN_POS_CENTER)

        self.nodes = nodes

        if pyexiv2Avaliable:
            self.ignoredTags = '.*0x0.*'
        else:
            self.ignoredTags = 'JPEGThumbnail|TIFFThumbnail|EXIF MakerNote'
            self.ignoredTags += '|MakerNote Unknown|EXIF Tag|MakerNote Tag'

        ## Set-up the Picture selector
        self.selector = PictureSelector(self.nodes)
        self.vbox2.pack_start
        self.vbox2.pack_start(self.selector)
        self.selector.connect("value_changed", self.on_selector_value_changed)
        self.selector.show()

        self.exifList = gtk.ListStore(str, str)

        self.treeview=gtk.TreeView(self.exifList)

        self.tagColumn = gtk.TreeViewColumn(_('Tag'))
        self.valueColumn = gtk.TreeViewColumn(_('Value'))

        self.treeview.append_column(self.tagColumn)
        self.treeview.append_column(self.valueColumn)

        self.cell = gtk.CellRendererText()

        self.tagColumn.pack_start(self.cell, True)
        self.valueColumn.pack_start(self.cell, True)

        self.tagColumn.add_attribute(self.cell, 'text', 0)
        self.valueColumn.add_attribute(self.cell, 'text', 1)

        # Gridlines commented out as libries shipped with current windows
        # jbrout pack do not support this, need new libs to enable.
        try:
            self.treeview.set_grid_lines(gtk.TREE_VIEW_GRID_LINES_BOTH)
        except:
            pass

        self.scrolledwindow1.add(self.treeview)

        self.scrolledwindow1.show_all()

        # Call set-photo to populate the table with the values for the first picture
        self.setPhoto(0)

    def setPhoto(self,i):
        self.exifList.clear()
        if os.path.isfile(self.nodes[i].file):
            if pyexiv2Avaliable:
                image=pyexiv2.Image(self.nodes[i].file)
                image.readMetadata()
                for key in image.exifKeys():
                    if re.match(self.ignoredTags, key) == None:
                        tag_details = image.tagDetails(key)
                        try:
                            self.exifList.append([tag_details[0],
                                image.interpretedExifValue(key)])
                        except:
                            print "Error on tag " + key
                for key in image.iptcKeys():
                    if re.match(self.ignoredTags, key) == None:
                        tag_details = image.tagDetails(key)
                        try:
                            self.exifList.append([tag_details[0], image[key]])
                        except:
                            print "Error on tag " + key
            else:
                f=open(self.nodes[i].file, 'rb')
                tags=exif.process_file(f)
                f.close()
                sortedTags=tags.keys()
                sortedTags.sort()
                for tag in sortedTags:
                    if re.match(self.ignoredTags, tag) == None:
                        try:
                            self.exifList.append([tag, tags[tag]])
                        except:
                            pass
            if len(self.exifList)==0:
                self.exifList.append([_('No Displayable EXIF Tags found in file!'), ''])
        else:
            self.exifList.append([_('Can not open file!'), ''])

    def on_winViewExif_delete_event(self, widget, *args):
        self.quit(False)

    def on_button_close_clicked(self, widget, *args):
        self.quit(False)

    def on_selector_value_changed(self, *args):
        self.setPhoto(self.selector.getValue())

def main():
    win_viewExif = WinViewExif()

    win_viewExif.loop()

if __name__ == "__main__":
    from libs.i18n import createGetText

    # make translation available in the gui/gtk
    GladeApp.bindtextdomain("jbrout",os.path.join(os.path.dirname(__file__), 'po'))

    # make translation available in the code
    __builtins__.__dict__["_"] = createGetText("jbrout",os.path.join(os.path.dirname(__file__), 'po'))

    main()
