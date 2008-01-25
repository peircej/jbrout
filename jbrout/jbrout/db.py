# -*- coding: utf-8 -*-

##
##    Copyright (C) 2005 manatlan manatlan[at]gmail(dot)com
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

from lxml.etree import Element,ElementTree
import lxml
import traceback
from datetime import datetime
#~ import cElementTree as ElementTree
import gc

import pygtk
pygtk.require('2.0')
import gtk
import gobject

from commongtk import Img,rgb
from tools import PhotoCmd
from libs import exif           # *!*
import os,re,sys,thread,shutil,stat,string

def walktree (top = ".", depthfirst = True):
    try:
        names = os.listdir(top)
    except WindowsError: #protected dirs in win
        names=[]

    if not depthfirst:
        yield top, names
    for name in names:
        try:
            st = os.lstat(os.path.join(top, name))
        except os.error:
            continue
        if stat.S_ISDIR(st.st_mode) and not name.startswith("."):
            for (newtop, children) in walktree (os.path.join(top, name), depthfirst):
                yield newtop, children
    if depthfirst:
        yield top, names
def cd2d(f): #yyyymmddhhiiss -> datetime
   return datetime(int(f[:4]),int(f[4:6]), int(f[6:8]),int(f[8:10]),int(f[10:12]),int(f[12:14]))

def dec(s): # ensure that a return from etree is in utf-8
    if s!=None:
        return s.decode("utf_8")


class DBPhotos:
    normalizeName = False
    autorotAtImport = False

    def __init__(self,file):
        if os.path.isfile(file):
            self.root = ElementTree(file=file).getroot()
        else:
            self.root = Element("db")
        self.file = file

        #==== simple basket convertion (without verification)
        # theses lines could be deleted in the future
        try:
            nodeB = self.root.xpath("/db/basket")[0]
        except:
            nodeB = None

        if nodeB:
            ln=nodeB.xpath("""/db/basket/p""")
            nodeB.xpath("..")[0].remove(nodeB) # adios old basket !
        #==== simple basket convertion (without verification)


    def setNormalizeName(self,v):
        DBPhotos.normalizeName = v

    def setNormalizeNameFormat(self,v):
        PhotoCmd.setNormalizeNameFormat(v)

    def setAutorotAtImport(self,v):
        DBPhotos.autorotAtImport = v


    def add(self,path,tags={}):
        assert type(path)==unicode
        assert os.path.isdir(path)
        path = os.path.normpath(path)

        ln = self.root.xpath(u"""//folder[@name="%s"]""" % path)
        assert len(ln)<=1
        if ln:
            nodeFolder = ln[0]
            filesInBasket = [i.file for i in self.getBasket(nodeFolder)]
            nodeFolder.xpath("..")[0].remove(nodeFolder)
        else:
            filesInBasket=[]

        files = []
        for (basepath, children) in walktree(path,False):
            for child in children:
                if child[-4:].lower() == ".jpg" and not child.startswith("."):
                    #~ file = os.path.join(basepath, child).decode( sys.getfilesystemencoding() )
                    file = os.path.join(basepath, child)
                    files.append(file)

        yield len(files)   # first yield is the total number of files

        for file in files:
            yield files.index(file)
            file = PhotoCmd.prepareFile(file,
                            needRename=DBPhotos.normalizeName,
                            needAutoRot=DBPhotos.autorotAtImport,
                            )
            self.__addPhoto( file ,tags,filesInBasket)

        ln = self.root.xpath(u"""//folder[@name="%s"]""" % path)
        if ln:
            yield FolderNode( ln[0] )
        else:
            yield None

    def __addPhoto(self,file,tags,filesInBasket):
        assert type(file)==unicode
        dir,name= os.path.split(file)

        try:
            nodeDir = self.root.xpath(u"""//folder[@name="%s"]""" % dir)[0]
        except:
            nodeDir=None

        if not nodeDir:
            rep=[]
            while 1:
                rep.append(dir)
                dir,n = os.path.split(dir)
                if not n: break
            rep.reverse()

            node = self.root
            for r in rep:
                try:
                    nodeDir = node.xpath(u"""folder[@name="%s"]""" % r)[0]
                except:
                    nodeDir = Element("folder", name=r)
                    node.append( nodeDir )

                    FolderNode(nodeDir)._updateInfo() # read comments

                node = nodeDir
            nodeDir=node


        newNode = Element("photo")
        nodeDir.append( newNode )

        node = PhotoNode(newNode)
        if file in filesInBasket:
            node.addToBasket()

        try:
            iii = PhotoCmd(file)
        except:
            # getback the stack trace exception
            import traceback
            err=traceback.format_exc()

            # remove the bad node
            nodeDir.remove(newNode)

            # and raise exception
            raise err+"\nPhoto has incorrect exif/iptc tags, can't be imported !!"
            return None
        else:
            importedTags=node.updateInfo( iii )
            for i in importedTags:  tags[i]=i # feed the dict of tags

            return node

    def getRootFolder(self):
        if len(self.root)>0:
            return FolderNode(self.root[0])

    def redoIPTC(self):
        """ refresh IPTC in file and db """
        ln = self.root.xpath(u"""//photo[t]""")
        for i in ln:
            p=PhotoNode(i)
            print p.name
            pc = PhotoCmd(p.file)
            pc._write()             # rewrite iptc in file
            p.updateInfo( pc )      # rewrite iptc in db.xml


    def getMinMaxDates(self):
        """ return a tuple of the (min,max) of photo dates
            or none if no photos
        """
        ln = self.root.xpath("//photo")
        if ln:
            ma = 11111111111111
            mi = 99999999999999
            for i in ln:
                a=int( i.attrib["date"] )
                ma = max(a,ma)
                mi = min(a,mi)
            return cd2d(str(mi)),cd2d(str(ma))


    def select(self,xpath,fromNode=None):
        ln=self.root.xpath(xpath)
        if ln:
            return [PhotoNode(i) for i in ln]
        else:
            return []

    def save(self):
        """ save the db, and a basket.txt file """
        fid = open(self.file,"w")
        fid.write("""<?xml version="1.0" encoding="UTF-8"?>""")
        ElementTree(self.root).write(fid,encoding="utf-8")
        fid.close()

        # save a "simple txt file" of basket'files near db.xml
        # (could be used in another prog ?)
        file = os.path.join( os.path.dirname(self.file),"basket.txt")
        if self.isBasket():
            list =[i.file for i in self.getBasket()]

            fid = open(file,"w")
            if fid:
                fid.write((u"\n".join(list)).encode("utf_8"))
                fid.close()
        else:
            try:
                os.unlink(file)
            except:
                pass
    #--------------------------------------------------------------------------------
    # basket methods
    #--------------------------------------------------------------------------------
    def isBasket(self):
        return len(self.root.xpath("//photo[@basket='1']"))>0

    def clearBasket(self):
        ln=self.getBasket()
        for i in ln:
            i.removeFromBasket()

    def getBasket(self,nodeFrom=None):
        if nodeFrom:
            return [PhotoNode(i) for i in nodeFrom.xpath("//photo[@basket='1']")]
        else:
            return [PhotoNode(i) for i in self.root.xpath("//photo[@basket='1']")]



class FolderNode(object):
    commentFile="album.txt"

    def __init__(self,n):
        assert n.tag in ["folder","db"]
        self.__node = n

    def __getName(self):    return os.path.basename(self.__node.attrib["name"])
    name = property(__getName)

    #~ def __getIsReadOnly(self):   return not os.access( self.file, os.W_OK)
    #~ isReadOnly = property(__getIsReadOnly)

    def __getFile(self):  return self.__node.attrib["name"]
    file = property(__getFile)

    def __getComment(self):
        ln = self.__node.xpath("c")
        if ln:
            return dec(ln[0].text)
        else:
            return ""
    comment = property(__getComment)

    def __getExpand(self):
        if "expand" in self.__node.attrib:
            return (self.__node.attrib["expand"]!="0")
        else:
            return True
    expand = property(__getExpand)

    def _getNode(self): # special
        return self.__node

    def getParent(self):
        return FolderNode( self.__node.xpath("..")[0] )

    def getFolders(self):
        ln=[FolderNode(i) for i in self.__node.xpath("folder")]
        ln.sort(cmp=lambda x,y: cmp(x.name.lower(),y.name.lower()))
        return ln

    def getPhotos(self):
        return [PhotoNode(i) for i in self.__node.xpath("photo")]
    def getAllPhotos(self):
        return [PhotoNode(i) for i in self.__node.xpath("descendant::photo")]
    def select(self,xpath):
        ln=self.__node.xpath(xpath)
        return [PhotoNode(i) for i in ln]

    def setComment(self,t):
        assert type(t)==unicode
        file = os.path.join(self.file,FolderNode.commentFile)
        if t=="": # if is the "kill comment"
            if os.path.isfile(file): # if files exists, kill it
                try:
                    os.unlink(file)
                    return True
                except:
                    return False

            return True
        else:
            fid=open( file ,"w" )
            if fid:
                fid.write( t.encode("utf_8") )
                fid.close()
                self._updateInfo()
                return True
            else:
                return False

    def _updateInfo(self):
        ln = self.__node.xpath("c")
        assert len(ln) in [0,1]
        if ln:
            nodeComment =ln[0]
        else:
            nodeComment =None

        comment = None
        file = os.path.join(self.file,FolderNode.commentFile)
        if os.path.isfile(file):
            fid=open( file ,"r" )
            if fid:
                comment = fid.read().decode("utf_8")
                fid.close()

        if comment:
            if nodeComment ==  None:
                nodeComment = Element("c")
                nodeComment.text = comment
                self.__node.append(nodeComment)
            else:
                nodeComment.text = comment
        else:
            if nodeComment !=  None:
                self.__node.remove(nodeComment)


    def setExpand(self,bool):
        if bool:
            self.__node.attrib["expand"] = "1"
        else:
            self.__node.attrib["expand"] = "0"

    def rename(self,newname):
        assert type(newname)==unicode
        oldname = self.file
        newname = os.path.join( os.path.dirname(oldname), newname )
        if not (os.path.isdir(newname) or os.path.isfile(newname)):
            try:
                shutil.move( oldname, newname )
                moved = True
            except os.error, detail:
                raise detail
                moved = False

            if moved:
                self.__node.attrib["name"] = newname

                ln = self.__node.xpath("descendant::folder")
                for i in ln:
                    i.attrib["name"] = newname + i.attrib["name"][len(oldname):]
                return True

        return False

    def createNewFolder(self,newname):
        assert type(newname)==unicode
        newname = os.path.join( self.file, newname )
        if not (os.path.isdir(newname) or os.path.isfile(newname)):
            try:
               os.mkdir( newname )
               created = True
            except os.error, detail:
               raise detail
               created = False

            if created:
                nodeDir = Element("folder", name=newname)
                self.__node.append( nodeDir )
                return FolderNode(nodeDir)
        return False

    def remove(self):
        self.__node.xpath("..")[0].remove(self.__node)

    def delete(self):
        try:
           shutil.rmtree( self.file )
           deleted = True
        except os.error, detail:
           raise detail
           deleted = False

        if deleted:
            self.remove()
            return True

        return False

    def moveToFolder(self,nodeFolder):
        assert nodeFolder.__class__ == FolderNode
        oldname = self.file
        newname = os.path.join(nodeFolder.file,self.name)
        if not (os.path.isdir(newname) or os.path.isfile(newname)):
            try:
                shutil.move( oldname, newname )
                moved = True
            except os.error, detail:
                raise detail
                moved = False

            if moved:
                self.__node.attrib["name"] = newname
                self.remove()
                nodeFolder.__node.append(self.__node)

                ln = self.__node.xpath("descendant::folder")
                for i in ln:
                    i.attrib["name"] = newname + i.attrib["name"][len(oldname):]
                return self
        return False


#~ def pixbuf_from_data(data):
    #~ loader = gtk.gdk.PixbufLoader ('jpeg')
    #~ loader.write (data, len (data))
    #~ pixbuf = loader.get_pixbuf ()
    #~ loader.close ()
    #~ return pixbuf

#~ def do_gui_operation(function, *args, **kw):
    #~ def idle_func():
        #~ gtk.threads_enter()
        #~ try:
            #~ function(*args, **kw)
            #~ return False
        #~ finally:
            #~ gtk.threads_leave()
    #~ gobject.idle_add(idle_func)


class Buffer:
    images={}
    #~ pixbufRefresh = gtk.gdk.pixbuf_new_from_file( "data/gfx/refresh.png" )
    pixbufRefresh = Img("data/gfx/refresh.png").pixbuf

    pbFolder = Img("data/gfx/folder.png").pixbuf
    pbBasket = Img("data/gfx/basket.png").pixbuf

    pbReadOnly = Img("data/gfx/check_no.png").pixbuf

    pbCheckEmpty = Img("data/gfx/check_false.png").pixbuf
    pbCheckInclude = Img("data/gfx/check_true.png").pixbuf
    pbCheckExclude = Img("data/gfx/check_no.png").pixbuf
    pbCheckDisabled = Img("data/gfx/check_disabled.png").pixbuf

    #~ @staticmethod
    #~ def __thread(file,callback,callbackRefresh,item):
        #~ do_gui_operation(Buffer.__fetcher,file,callback,callbackRefresh,item)


    #~ @staticmethod
    #~ def __fetcher(file,callback,callbackRefresh,item):
        #~ Buffer.images[file] = callback()
        #~ if callbackRefresh and item>=0:
            #~ callbackRefresh(item)

    #~ @staticmethod
    #~ def get(file,callback,callbackRefresh=None,item=None):
        #~ """
        #~ send a signal "refreshItem"(item) to object
        #~ """
        #~ if file in Buffer.images:
            #~ return Buffer.images[file]
        #~ else:
            #~ thread.start_new_thread(Buffer.__thread, (file,callback,callbackRefresh,item) )
            #~ return Buffer.pixbufRefresh

    @staticmethod
    def remove(file):
        if file in Buffer.images:
            del(Buffer.images[file])
            return True
        else:
            return False
    @staticmethod
    def clear():
        size = JBrout.conf["thumbsize"] or 160
        Buffer.images={}
        Buffer.pixbufNF = Img("data/gfx/imgNotFound.png").resizeC(size).pixbuf
        Buffer.pixbufNFNE = Img("data/gfx/imgNotFound.png").resizeC(size, rgb(255,0,0) ).pixbuf

        Buffer.pixbufNT = Img("data/gfx/imgNoThumb.png").resizeC(size).pixbuf
        Buffer.pixbufNTNE = Img("data/gfx/imgNoThumb.png").resizeC(size,rgb(255,0,0)).pixbuf

        Buffer.pixbufERR = Img("data/gfx/imgError.png").resizeC(size).pixbuf
        Buffer.pixbufERRNE = Img("data/gfx/imgError.png").resizeC(size,rgb(255,0,0)).pixbuf

#~ class PhotoFile:
    #~ @staticmethod
    #~ def generate(path):
        #~ list=[]
        #~ for i in os.listdir(path):
            #~ if i[-4:].lower()==".jpg":
                #~ list.append( PhotoFile(os.path.join(path,i)) )
        #~ return list
    #~ generate = staticmethod(generate)

    #~ def __init__(self,f):
        #~ self.file = f
        #~ self.name = os.path.basename(f)

    #~ def getThumb(self):
        #~ try:
            #~ i=Img(thumb=self.file)
            #~ data = i.resizeC(160).getStreamJpeg().read()
            #~ return pixbuf_from_data(data)
        #~ except:
            #~ return None


class PhotoNode(object):

    """
      Class PhotoNode
      to manipulate a node photo in the dom of album.xml.
    """
    def __init__(self,node):
        assert node.tag == "photo"
        self.__node = node

    def __getName(self):    return self.__node.attrib["name"]
    name = property(__getName)

    def __getfolderName(self):    return os.path.basename(self.folder)
    folderName = property(__getfolderName)

    def __getIsReadOnly(self):    return not os.access( self.file, os.W_OK)
    isReadOnly = property(__getIsReadOnly)


    def __getTags(self):
        l=[dec(i.text) for i in self.__node.xpath("t")]
        l.sort()
        return l
    tags = property(__getTags)

    def __getComment(self):
        ln = self.__node.xpath("c")
        if ln:
            return dec(ln[0].text)
        else:
            return ""
    comment = property(__getComment)

    def __getDate(self): return self.__node.attrib["date"]  # if exif -> exifdate else filedate
    date = property(__getDate)

    def __getResolution(self): return self.__node.attrib["resolution"]
    resolution = property(__getResolution)

    def __getReal(self): return self.__node.attrib["real"]  # if exifdate -> true else false
    real = property(__getReal)

    def __getFolder(self):
        na=dec(self.__node.xpath("..")[0].attrib["name"])
        assert type(na)==unicode
        return na
    folder = property(__getFolder)

    def __getFile(self):  return dec(os.path.join(self.__getFolder(),self.__getName()))
    file = property(__getFile)

    def getParent(self):
        return FolderNode( self.__node.xpath("..")[0] )

    def __getIsInBasket(self):  return (self.__node.get("basket")=="1")
    isInBasket = property(__getIsInBasket)


    def addToBasket(self):
        self.__node.set("basket","1")

    def removeFromBasket(self):
        if self.isInBasket:
            del(self.__node.attrib["basket"])

    #~ def __eq__(self,p):
        #~ assert p.__class__==PhotoNode
        #~ return self.file == p.file
    # throw a bug in lxml ?!?! ;-(

    def getThumb(self):
        if self.real == "yes":  # real photo (exifdate !)
            backGroundColor=None
            pb_nothumb = Buffer.pixbufNT
            pb_notfound =Buffer.pixbufNF
            pb_error   =Buffer.pixbufERR
        else:                   # photo with no exif or with no exifdate
            backGroundColor=rgb(255,0,0)
            pb_nothumb = Buffer.pixbufNTNE
            pb_notfound =Buffer.pixbufNFNE
            pb_error   =Buffer.pixbufERRNE
        try:
            i=Img(thumb=self.file)
            #~ pb= i.resizeC(JBrout.conf["thumbsize"] or 160,backGroundColor).pixbuf
            pb= i.resizeC(160,backGroundColor).pixbuf
        except IOError: # 404
            pb= pb_notfound
        except KeyError: # no exif
            pb= pb_nothumb
        except:
            # big error in "exif.py"
            print >>sys.stderr,'-'*60
            traceback.print_exc(file=sys.stderr)
            print >>sys.stderr,'-'*60
            pb=pb_error

        return pb

    def getImage(self):
        return gtk.gdk.pixbuf_new_from_file(self.file)

    def giveMeANewName(self):   # todo
        n,ext = os.path.splitext(self.name)
        mo= re.match("(.*)\((\d+)\)",n)
        if mo:
            n=mo.group(1)
            num=int(mo.group(2)) +1
        else:
            num=1

        return "%s(%d)%s" % (n,num,ext)

    def moveToFolder(self,nodeFolder):
        assert nodeFolder.__class__ == FolderNode

        name = self.name
        while os.path.isfile(os.path.join(nodeFolder.file,name) ):
            name=self.giveMeANewName()

        try:
            shutil.move( self.file, os.path.join(nodeFolder.file,name) )
            moved=True
        except os.error, detail:
            raise detail
            moved=False

        if moved:
            self.__node.attrib["name"] = name
            self.__node.xpath("..")[0].remove(self.__node)
            nf = nodeFolder._getNode()
            nf.append(self.__node)
            return True

    def rotate(self,sens):
        assert sens in ["R","L"]

        pc = PhotoCmd(self.file)
        pc.rotate(sens)
        self.updateInfo(pc)

    def setComment(self,txt):
        assert type(txt)==unicode

        pc = PhotoCmd(self.file)
        if pc.addComment(txt):
            self.updateInfo(pc)

    def addTag(self,tag):
        assert type(tag)==unicode

        pc = PhotoCmd(self.file)
        if pc.add(tag):
            self.updateInfo(pc)

    def addTags(self,tags):
        assert type(tags)==list

        pc = PhotoCmd(self.file)
        if pc.addTags(tags):
            self.updateInfo(pc)

    def delTag(self,tag):
        assert type(tag)==unicode

        pc = PhotoCmd(self.file)
        if pc.sub(tag):
            self.updateInfo(pc)

    def clearTags(self):
        pc = PhotoCmd(self.file)
        if pc.clear():
            self.updateInfo(pc)

    def rebuildThumbnail(self):
        pc = PhotoCmd(self.file)
        pc.rebuildExifTB()
        self.updateInfo(pc)

    def copyTo(self,path,resize=None, keepInfo=True):
        """ copy self to the path "path", and return its newfilename or none
            by default, it keeps IPTC/THUMB/EXIF, but it can be removed by setting
            keepInfo at False. In all case, new file keep its filedate system

            image can be resized/recompressed (preserving ratio) if resize
            (which is a tuple=(size,qual)) is provided:
                if size is a float : it's a percent of original
                if size is a int : it's the desired largest side
                qual : is the percent for the quality
        """
        assert type(path)==unicode, "photonod.copyTo() : path is not unicode"
        dest = os.path.join( path, self.name)

        cpt=0
        while os.path.isfile(dest):
            dest = os.path.join( path, self.giveMeANewName() )
            cpt+=1
            if cpt>10: return None  #security

        if resize:
            assert len(resize)==2
            size,qual = resize
            assert type(size) in [int,float]

            pb = self.getImage() # a gtk.PixBuf
            (wx,wy) = pb.get_width(),pb.get_height()


            # compute the new size -> wx/wy
            if type(size)==float:
                # size is a percent
                size = int(size*100)
                wx = int(wx*size / 100)
                wy = int(wy*size / 100)

            else:
                # size is the largest side in pixels
                if wx>wy:
                    # format landscape
                    wx, wy = size, (size * wy)/wx
                else:
                    # format portrait
                    wx, wy = (size * wx)/wy, size


            pb = pb.scale_simple(wx,wy,3)   # 3= best quality (gtk.gdk.INTERP_HYPER)
            pb.save(dest, "jpeg", {"quality":str(int(qual))})

            if keepInfo:
                pc = PhotoCmd(self.file)
                pc.copyInfoTo(dest)
            del(pb)
            gc.collect() # so it cleans pixbufs
        else:
            shutil.copy2(self.file,dest)
            if not keepInfo:
                # we must destroy info
                PhotoCmd(dest).destroyInfo()

        return dest

    def getInfoFrom(self,copy):
        """ rewrite info from a 'copy' to the file (exif, iptc, ...)
            and rebuild thumb
            (used to ensure everything is back after a run in another program
             see plugin 'touch')
        """
        pc=PhotoCmd(copy)
        pc.copyInfoTo(self.file)

        #and update infos
        # generally, it's not necessary ... but if size had changed, jhead
        # correct automatically width/height exif, so we need to put back in db
        pc = PhotoCmd(self.file)
        self.updateInfo(pc)

    #~ def repair(self):
        #~ pc = PhotoCmd(self.file)
        #~ pc.repair()                 # kill exif tags ;-(
        #~ pc.rebuildExifTB()          # recreate "fake exif tags" with exifutils and thumbnails
        #~ self.updateInfo(pc)

    def redate(self,w,d,h,m,s ):
        pc = PhotoCmd(self.file)
        pc.redate(w,d,h,m,s)
        self.updateInfo(pc)

        #photo has been redated
        #it should be renamed if in config ...
        if DBPhotos.normalizeName:
            file = PhotoCmd.normalizeName(self.file)
            if file != self.file:
                self.__node.attrib["name"] = os.path.basename(file)
                pc = PhotoCmd(self.file)
                self.updateInfo(pc)

        return True

    def updateInfo(self,pc):
        """ feel the node with REALS INFOS from "pc"(PhotoCmd)
            return the tags
        """
        assert pc.__class__==PhotoCmd

        wasInBasket = self.isInBasket

        self.__node.clear()
        self.__node.attrib["name"]=os.path.basename(pc.file)
        self.__node.attrib["resolution"]=pc.resolution

        if pc.exifdate:
            self.__node.attrib["date"]=pc.exifdate
            self.__node.attrib["real"]="yes"
        else:
            self.__node.attrib["date"]=pc.filedate
            self.__node.attrib["real"]="no"


        if pc.tags:
            for tag in pc.tags:
                nodeTag = Element("t")
                nodeTag.text = tag
                self.__node.append(nodeTag)
        if pc.comment:
            nodeComment = Element("c")
            nodeComment.text = pc.comment
            self.__node.append(nodeComment)

        if wasInBasket:
            self.addToBasket()

        return pc.tags

    def getInfo(self):
        """
        get real infos from photocmd
        """
        pc = PhotoCmd(self.file)
        info={}
        info["tags"] = pc.tags
        info["comment"] = pc.comment
        info["exifdate"] = pc.exifdate
        info["filedate"] = pc.filedate
        info["resolution"] = pc.resolution
        info["readonly"] = pc.readonly
        info["filesize"] = os.stat(self.file)[6]

        return info

    def getExifInfo(self):
        """ return the result of jhead """
        pc=PhotoCmd(self.file)
        return pc.getExifInfo()

    def getThumbSize(self):
        """Get the size (width,height) of the thumbnail"""
        try:
            thumbnail=Img(thumb=self.file)
            return (thumbnail.width,thumbnail.height)
        except IOError: # 404
            return (-1,-1)


    def delete(self):
        try:
           os.unlink( self.file )
           deleted = True
        except os.error, detail:
           raise detail
           deleted = False

        if deleted:
            self.__node.xpath("..")[0].remove(self.__node)
            return True

        return False


# ============================================================================================
class DBTags:
# ============================================================================================
   def __init__(self,file):
        if os.path.isfile(file):
            self.root = ElementTree(file=file).getroot()
        else:
            self.root = Element("tags")
        self.file = file

   def getAllTags(self):
        """ return list of tuples (tag, parent catg)"""
        l=[(n.text,n.xpath("..")[0].get("name")) for n in self.root.xpath("//tag")]
        l.sort(cmp= lambda x,y: cmp(x[0].lower(),y[0].lower()))
        return l

   def save(self):
        fid = open(self.file,"w")
        fid.write("""<?xml version="1.0" encoding="UTF-8"?>""")
        ElementTree(self.root).write(fid,encoding="utf-8")
        fid.close()

   #def getTagForKey(self,key):
   #    """ return the tag as utf_8 for the key 'key' """
   #    ln=self.root.xpath("//tag[@key='%s']"%key)
   #    if ln:
   #        assert len(ln)==1
   #        return dec(ln[0].text)

   #~ def update(self, tg):
      #~ nc = self.dom.selectSingleNode("//catg[@name='IMPORTEDTAGS']")
      #~ if not nc:
         #~ nc=self.dom.createElement("catg")
         #~ nc.setAttribute( "name","IMPORTEDTAGS")

      #~ newtags=False
      #~ st = self.getTags()
      #~ for i in tg:
         #~ if i in st:
            #~ pass
         #~ else:
            #~ n=self.dom.createElement("tag")
            #~ n.setAttribute( "name",i)
            #~ nc.appendChild(n)
            #~ newtags = True

      #~ if newtags:
         #~ self.dom.documentElement.appendChild(nc)
         #~ self.win.treeTags.init()
         #~ msgBox(_("There are New Imported Tags"))
   def getRootTag(self):
        return CatgNode(self.root)

   def updateImportedTags( self, importedTags ):
        assert type(importedTags)==list

        r = self.getRootTag()
        existingTags = [i.name for i in r.getAllTags()]

        # compare existing and imported tags -> newTags
        newTags=[]
        for tag in importedTags:
            if tag not in existingTags:
                newTags.append(tag)

        if newTags:
            # create a category imported
            nom = u"Imported Tags"
            while 1:
                nc=r.addCatg(nom)
                if nc!=None:
                    break
                else:
                    nom+=u"!"

            for tag in newTags:
                ret=nc.addTag(tag)
                assert ret!=None,"tag '%s' couldn't be added"%tag

        return len(newTags)

class TagNode(object):
    def __init__(self,n):
        assert n.tag == "tag"
        self.__node = n

    def __getName(self): return dec(self.__node.text)
    name = property(__getName)

    def __getKey(self): return dec(self.__node.get("key"))
    def __setKey(self,v): self.__node.set("key",v)
    key = property(__getKey,__setKey)

    def remove(self):
        self.__node.xpath("..")[0].remove(self.__node)

    def moveToCatg(self,c):
        assert type(c)==CatgNode
        self.remove()
        c._appendToCatg(self.__node)


class CatgNode(object):
    def __init__(self,n):
        assert n.tag == "tags"
        self.__node = n

    def __getName(self):
        if "name" in self.__node.attrib:
            return dec(self.__node.attrib["name"])
        else:
            return u"Tags"
    name = property(__getName)

    def __getExpand(self):
        if "expand" in self.__node.attrib:
            return (self.__node.attrib["expand"]!="0")
        else:
            return True
    expand = property(__getExpand)

    def getTags(self):
        l=[TagNode(i) for i in self.__node.xpath("tag")]
        l.sort( cmp=lambda x,y: cmp(x.name,y.name) )
        return l
    def getCatgs(self):
        return [CatgNode(i) for i in self.__node.xpath("tags")]

    def getAllTags(self):
        l= self.getTags()
        for i in self.getCatgs():
            l.extend( i.getAllTags() )
        l.sort(cmp=lambda x,y: cmp(x.name,y.name))
        return l

    def addTag(self,t):
        assert type(t)==unicode
        if self.isUnique("tag",t):
            n = Element("tag")
            n.text = t
            self.__node.append(n)
            return TagNode(n)

    def remove(self):
        self.__node.xpath("..")[0].remove(self.__node)

    def moveToCatg(self,c):
        self.remove()
        c._appendToCatg(self.__node)

    def _appendToCatg(self,element):
        self.__node.append(element)

    def addCatg(self,t):
        assert type(t)==unicode
        if self.isUnique("tags",t):
            n = Element("tags",name=t)
            self.__node.append(n)
            return CatgNode(n)

    def setExpand(self,bool):
        if bool:
            self.__node.attrib["expand"] = "1"
        else:
            self.__node.attrib["expand"] = "0"

    def isUnique(self,type,name):
        if type=="tag":
            ln=[dec(i.text) for i in self.__node.xpath("//tag")]
        else:
            ln=[CatgNode(i).name for i in self.__node.xpath("//tags")]
        return name not in ln




#~ from plugger import PluginsManager
from plugins import JPlugins
import sys,os
# ============================================================================================
class Conf(object):
# ============================================================================================
    def __getLines(self):
        try:
            fid = open( self.__file,"r")
            buf = fid.readlines()
            fid.close()
        except:
            buf=[]
        return buf


    def __init__(self,file):
      self.__file = file
      self.__vars = {}

      buf = self.__getLines()

      for ligne in buf:
            ligne = ligne.strip()
            if ligne and ligne[0] not in ("#",";"):
                p = ligne.find("=")
                if p>0:
                    val = ligne[p+1:].strip()
                    if val.isdigit():
                        val = int(val)
                    self.__vars[ ligne[:p].strip() ] = val

    def __getitem__(self,n):
      if n in self.__vars:
         return self.__vars[n]
      #~ else:
         #~ raise "attribul global inconnu"

    def __setitem__(self,n,v):
        self.__vars[n] =v

    def save(self):
        #~ fid = open( self.__file,"w")
        #~ for k in self.__vars:
            #~ fid.write("%s=%s\r\n" % (k,str(self.__vars[k])) )
        #~ fid.close()

        vars = {}
        vars.update(self.__vars)

        buf = self.__getLines()

        # subsitute lines (buf -> ligne)
        news=[]
        for ligne in buf:
            ligne = ligne.strip("\r\n \t")
            if ligne and ligne[0] not in ("#",";"):
                p = ligne.find("=")
                var = ligne[:p].strip()
                if var in vars:
                    ligne = "%s=%s" % (var,str(vars[var]))
                    del(vars[var])

            news.append(ligne)

        # and add the rest .... some news variables
        for i in vars:
            news.append("%s=%s" % (i,str(vars[i])))

        # and write it to disk
        fid = open( self.__file,"w")
        for i in news:
            fid.write(i+"\n")
        fid.close()

class JBrout:
    __lockFile = "jbrout.lock"

    @staticmethod
    def lockOn():
        """ create the lock file, return True if it can"""
        file = os.path.join(JBrout.getHomeDir("jbrout"),JBrout.__lockFile)
        if os.path.isfile(file):
            print file
            return False
        else:
            open(file,"w").write("")
            return True

    @staticmethod
    def lockOff():
        """ delete the lockfile """
        file = os.path.join(JBrout.getHomeDir("jbrout"),JBrout.__lockFile)
        if os.path.isfile(file):
            os.unlink(file)

    @staticmethod
    def getHomeDir(mkdir=None):
        """
        Return the "Home dir" of the system (if it exists), or None
        (if mkdir is set : it will create a subFolder "mkdir" if the path exist,
        and will append to it (the newfolder can begins with a "." or not))
        """
        maskDir=False
        try:
            #windows NT,2k,XP,etc. fallback
            home = os.environ['APPDATA']
            if not os.path.isdir(home): raise
            maskDir=False
        except:
            try:
                #all user-based OSes
                home = os.path.expanduser("~")
                if home == "~": raise
                if not os.path.isdir(home): raise
                maskDir=True
            except:
                try:
                    # freedesktop *nix ?
                    home = os.environ['XDG_CONFIG_HOME']
                    if not os.path.isdir(home): raise
                    maskDir=False
                except:
                    try:
                        #*nix fallback
                        home = os.environ['HOME']
                        if os.path.isdir(home):
                            conf = os.path.join(home,".config")
                            if os.path.isdir(conf):
                                home = conf
                                maskDir=False
                            else:
                                # keep home
                                maskDir=True
                        else:
                            raise
                    except:
                        #What os are people using?
                        home = None

        if home:
            if mkdir:
                if maskDir:
                    newDir = "."+mkdir
                else:
                    newDir = mkdir

                home = os.path.join(home,newDir)
                if not os.path.isdir(home):
                    os.mkdir(home)

            return home


    @staticmethod
    def getConfFile(name):
        if os.path.isfile(name):
            # the file exists in the local "./"
            # so we use it first
            return name
        else:
            # the file doesn't exist in the local "./"
            # it must exist in the "jbrout" config dir
            home = JBrout.getHomeDir("jbrout")
            if home:
                # there is a "jbrout" config dir
                # the file must be present/created in this dir
                return os.path.join(home,name)
            else:
                # there is not a "jbrout" config dir
                # the file must be present/created in this local "./"
                return name
    @staticmethod
    def init(modify):

        JBrout.modify = modify


        # initialisation de ".db"
        #======================================================================
        JBrout.db = DBPhotos( JBrout.getConfFile("db.xml") )

        # initialisation de ".tags"
        #======================================================================
        JBrout.tags = DBTags( JBrout.getConfFile("tags.xml") )

        # initialisation de ".conf"
        #======================================================================
        JBrout.conf = Conf( JBrout.getConfFile("jbrout.conf") )

        # initialisation de ".conf"
        #======================================================================
        JBrout.toolsFile = JBrout.getConfFile("tools.txt")

        # initialisation de ".plugins"
        #======================================================================
        jbroutHomePath = JBrout.getHomeDir("jbrout")

        JBrout.plugins = JPlugins(jbroutHomePath)

if __name__ == "__main__":
    #~ doc = lxml.etree.fromstring("<foo>fd<bar>kk</bar>oi</foo>")
    #~ r = doc.xpath('/foo/bar')
    #~ print len(r)
    #~ print r[0].tag
    #~ print doc.tag
    #~ print doc.text

    db = DBPhotos("kif.xml")
    db.clearBasket()
    #~ db.add("/home/manatlan/Desktop/tests")

    #~ print db.cpt()
    #~ db.save()
    #~ print db.getRootBasket()

    #~ db=DBTags()
    #~ r=db.getRootTag()

    #~ for i in r.getTags():
        #~ print type(i),i.name
    #~ for i in r.getCatgs():
        #~ print type(i),i.name

    #~ ln = db.select("//photo")
    #~ for i in ln:
        #~ print i.name, i.file
    #~ print ln[0].getParent()
