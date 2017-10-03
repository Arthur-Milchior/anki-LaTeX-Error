# -*- coding: utf-8 -*-

"""Copyright: Arthur Milchior arthur@milchior.fr
License: GNU GPL, version 3 or later; http://www.gnu.org/copyleft/gpl.html
Feel free to contribute to the code on https://github.com/Arthur-Milchior/anki-LaTeX-Error

Add a tag LaTeXError to each cards which have a LaTeX error. Remove this tags from cards which doesn't have any LaTeX error.
"""

from anki.hooks import addHook
from aqt.utils import tooltip, isWin, isMac
from anki.utils import checksum, intTime
from anki.media import MediaManager
import re
import unicodedata
import anki.notes
import os
from anki.latex import regexps, _latexFromHtml, build, _buildImg
from anki.consts import *

def mungeQA(html, type, fields, model, data, col):
    "Convert TEXT with embedded latex tags to image links. Returns the HTML and whether an error occurred."
    error = False
    for match in regexps['standard'].finditer(html):
        link, er = _imgLink(col, match.group(1), model)
        html = html.replace(match.group(), link)
        error = error or er
    for match in regexps['expression'].finditer(html):
        link, er = _imgLink(
            col, "$" + match.group(1) + "$", model)
        html = html.replace(match.group(), link)
        error = error or er
    for match in regexps['math'].finditer(html):
        link, er = _imgLink(
            col,
            "\\begin{displaymath}" + match.group(1) + "\\end{displaymath}", model)
        html = html.replace(match.group(), link)
        error = error or er
    return html, error

def _imgLink(col, latex, model):
    """A pair containing:
    An img link for LATEX, creating if necesssary. 
    Whether an error occurred."""
    txt = _latexFromHtml(col, latex)

    if model.get("latexsvg", False):
        ext = "svg"
    else:
        ext = "png"

    # is there an existing file?
    fname = "latex-%s.%s" % (checksum(txt.encode("utf8")), ext)
    link = '<img class=latex src="%s">' % fname
    if os.path.exists(fname):
        return (link,False)

    # building disabled?
    if not build:
        return ("[latex]%s[/latex]" % latex,False)

    err = _buildImg(col, txt, fname, model)
    if err:
        return (err,True)
    else:
        return (link,False)

def filesInStr(s, mid, string, nid, includeRemote=False):
    l = []
    model = s.col.models.get(mid)
    strings = []
    someError = False
    if model['type'] == MODEL_CLOZE and "{{c" in string:
        # if the field has clozes in it, we'll need to expand the
        # possibilities so we can render latex
        strings = s._expandClozes(string)
    else:
        strings = [string]
    for string in strings:
        # handle latex
        (string,error) = mungeQA(string, None, None, model, None, s.col)
        someError = error or someError
        # extract filenames
        for reg in s.regexps:
            for match in re.finditer(reg, string):
                fname = match.group("fname")
                isLocal = not re.match("(https?|ftp)://", fname.lower())
                if isLocal or includeRemote:
                    l.append(fname)
    if someError:
        note = s.col.getNote(nid)
        note.addTag("LaTeXError")
#        tooltip("Error on card %s."% nid)
        note.flush()
    return (l,someError)

def check(self, local=None):
    "Return (missingFiles, unusedFiles, numberError)."
    totalError=0
    mdir = self.dir()
    # gather all media references in NFC form
    allRefs = set()
    for nid, mid, flds in self.col.db.execute("select id, mid, flds from notes"):
        (noteRefs,error) = filesInStr(self,mid, flds, nid)
        if error :
            totalError +=1
        # check the refs are in NFC
        for f in noteRefs:
            # if they're not, we'll need to fix them first
            if f != unicodedata.normalize("NFC", f):
                self._normalizeNoteRefs(nid)
                noteRefs = self.filesInStr(mid, flds,nid)
                break
        allRefs.update(noteRefs)
    # loop through media folder
    unused = []
    if local is None:
        files = os.listdir(mdir)
    else:
        files = local
    renamedFiles = False
    dirFound = False
    warnings = []
    for file in files:
        if not local:
            if not os.path.isfile(file):
                # ignore directories
                dirFound = True
                continue
        if file.startswith("_"):
            # leading _ says to ignore file
            continue
        if self.hasIllegal(file):
            name = file.encode(sys.getfilesystemencoding(), errors="replace")
            name = str(name, sys.getfilesystemencoding())
            warnings.append(
                _("Invalid file name, please rename: %s") % name)
            continue
        nfcFile = unicodedata.normalize("NFC", file)
        # we enforce NFC fs encoding on non-macs; on macs we'll have gotten
        # NFD so we use the above variable for comparing references
        if not isMac and not local:
            if file != nfcFile:
                # delete if we already have the NFC form, otherwise rename
                if os.path.exists(nfcFile):
                    os.unlink(file)
                    renamedFiles = True
                else:
                    os.rename(file, nfcFile)
                    renamedFiles = True
                file = nfcFile
        # compare
        if nfcFile not in allRefs:
            unused.append(file)
        else:
            allRefs.discard(nfcFile)
    # if we renamed any files to nfc format, we must rerun the check
    # to make sure the renamed files are not marked as unused
    if renamedFiles:
        return self.check(local=local)
    nohave = [x for x in allRefs if not x.startswith("_")]
    # make sure the media DB is valid
    try:
        self.findChanges()
    except DBError:
        self._deleteDB()
    if dirFound:
        warnings.append(
            _("Anki does not support files in subfolders of the collection.media folder."))
#    if totalError>0:
    warnings.append(
       _("There are %s cards with a latex error.")% totalError)
    return (nohave, unused, warnings)

MediaManager.check = check
