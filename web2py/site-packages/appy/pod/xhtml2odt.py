# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
# Appy is a framework for building applications in the Python language.
# Copyright (c) 2007-2015 Gaetan Delannay
# Distributed under the GNU General Public License.
# Contributors: Gauthier Bastien, Fabio Marcuzzi, IMIO.

# ------------------------------------------------------------------------------
import xml.sax, time, random
from appy.pod import *
from appy.pod.odf_parser import OdfEnvironment
from appy.pod.styles_manager import \
     Style, BulletedProperties, NumberedProperties
from appy.pod.doc_importers import px2cm
from appy.shared.xml_parser import XmlEnvironment, XmlParser, escapeXml
from appy.shared.utils import WhitespaceCruncher, formatNumber, addPair
from appy.shared.css import CssStyles, CssValue

# To which ODT tags do HTML tags correspond ?
HTML_2_ODT = {
  'h1':'text:h', 'h2':'text:h', 'h3':'text:h', 'h4':'text:h', 'h5':'text:h',
  'h6':'text:h', 'p':'text:p', 'div': 'text:p', 'blockquote': 'text:p',
  'b':'text:span', 'i':'text:span', 'strong':'text:span', 'strike':'text:span',
  's':'text:span', 'u':'text:span', 'em': 'text:span', 'sub': 'text:span',
  'sup': 'text:span', 'br': 'text:line-break', 'span': 'text:span',
  'code': 'text:span', 'font': 'text:span',
  'td': 'table:table-cell', 'th': 'table:table-cell'}
STYLED_INNER_TAGS = ('b', 'i', 'strong', 'strike', 's', 'u', 'em', 'sub', 'sup',
                     'span', 'a', 'q', 'code')
INNER_TAGS_NO_BR = STYLED_INNER_TAGS + ('acronym',)
INNER_TAGS = INNER_TAGS_NO_BR + ('br',)
TABLE_CELL_TAGS = ('td', 'th')
TABLE_COL_TAGS = TABLE_CELL_TAGS + ('col',)
TABLE_ROW_TAGS = ('tr', 'colgroup')
OUTER_TAGS = TABLE_CELL_TAGS + ('li',)
PARA_TAGS = ('p', 'div', 'blockquote')
# The following elements can't be rendered inside paragraphs
NOT_INSIDE_P = XHTML_HEADINGS + XHTML_LISTS + ('table',)
NOT_INSIDE_P_OR_P = NOT_INSIDE_P + PARA_TAGS
NOT_INSIDE_LIST = ('table',)
IGNORABLE_TAGS = ('meta', 'title', 'style', 'script')

# ------------------------------------------------------------------------------
class HtmlElement:
    '''Every time an HTML element is encountered during the SAX parsing,
       an instance of this class is pushed on the stack of currently parsed
       elements.'''
    elemTypes = {'p':'para', 'div':'para', 'blockquote': 'para',
                 'li':'para', 'ol':'list', 'ul':'list'}

    # Prototypical instances
    protos = {}

    def __init__(self, elem, attrs, parent=None):
        self.elem = elem
        # Store a reference to the parent element if known
        self.parent = parent
        # Keep "class" attribute (useful for finding the corresponding ODT
        # style) in some cases. Normally, basic XmlElement class stores attrs,
        # but for a strange reason those attrs are back to None (probably for
        # performance reasons they become inaccessible after a while).
        self.classAttr = None
        if attrs.has_key('class'):
            self.classAttr = attrs['class']
        # Extract some useful attrs
        self.attrs = None
        if (elem == 'ol') and attrs.has_key('start'):
            self.attrs = {'start': int(attrs['start'])}
        self.tagsToReopen = [] # When the HTML element corresponding to self
        # is completely dumped, if there was a problem related to tags
        # inclusion, we may need to dump start tags corresponding to
        # tags that we had to close before dumping this element. This list
        # contains HtmlElement instances.
        self.tagsToClose = [] # Before dumping the closing tag corresponding
        # to self, we may need to close other tags (ie closing a paragraph
        # before closing a cell). This list contains HtmlElement instances.
        self.elemType = self.elem
        if self.elemTypes.has_key(self.elem):
            self.elemType = self.elemTypes[self.elem]
        # If a conflict occurs on this element, we will note it
        self.isConflictual = False
        # Sometimes we must remember the ODT style that has been computed and
        # applied to this HTML element (for lists).
        self.odStyle = None
        # For TD tags, we must know what style to apply to inner paragraphs
        self.innerStyle = (elem == 'td') and 'podCellContent' or None
        # Must we only keep tag content and remove the tag itself ?
        self.removeTag = False
        # Was content already dumped from this tag into the result ?
        self.contentDumped = False
        # Was content already dumped from this tag or any of its sub-tags into
        # the result ?
        self.contentDumpedOrSub = False
        # Inner attributes are those from a removed inner tag
        self.innerAttributes = None

    def getOdfTag(self, env):
        '''Gets the raw ODF tag that corresponds to me'''
        res = HTML_2_ODT.get(self.elem, '')
        if res: return res
        if self.elem == 'a':
            res += '%s:a' % env.textNs
        elif self.elem in XHTML_LISTS:
            res += '%s:list' % env.textNs
        elif self.elem == 'li':
            res += '%s:list-item' % env.textNs
        elif self.elem == 'table':
            res += '%s:table' % env.tableNs
        elif self.elem == 'thead':
            res += '%s:table-header-rows' % env.tableNs
        elif self.elem == 'tr':
            res += '%s:table-row' % env.tableNs
        return res

    def getOdfTags(self, env):
        '''Gets the start and end tags corresponding to p_self'''
        tag = self.getOdfTag(env)
        if not tag: return (None, None)
        return ('<%s>' % tag, '</%s>' % tag)

    def setConflictual(self):
        '''Note p_self as conflictual'''
        self.isConflictual = True
        return self

    def getPath(self):
        '''Return this element's "absolute path" within the XHTML tree'''
        res = self.elem
        if self.parent:
            res = '%s>%s' % (self.parent.getPath(), res)
        return res

    def getConflictualElements(self, env, attrs):
        '''p_self was just parsed. In some cases, this element can't be dumped
           in the result because there are conflictual elements among previously
           parsed opening elements (p_env.currentElements). For example, if we
           just dumped a "p", we can't dump a table within the "p". Such
           constraints do not hold in XHTML code but hold in ODF code.'''
        if not env.currentElements: return ()
        parent = env.getCurrentElement()
        # Special case: check elements that can't be found within a "li"/"td".
        # Instead of being noted as "conflictual", note that we must keep
        # these element's contents but remove the surrounding tags.
        if (parent.elem in ('li', 'td')) and (self.elem in PARA_TAGS):
            self.removeTag = True
            parent.addInnerAttributes(attrs)
            return ()
        # Check elements that can't be found within a paragraph
        if (parent.elemType == 'para') and (self.elem in NOT_INSIDE_P_OR_P):
            return (parent.setConflictual(),)
        # Check inner paragraphs
        elif (parent.elem in INNER_TAGS) and (self.elemType == 'para'):
            res = [parent.setConflictual()]
            if len(env.currentElements) > 1:
                i = 2
                visitParents = True
                while visitParents:
                    try:
                        nextParent = env.currentElements[-i]
                        i += 1
                        res.insert(0, nextParent.setConflictual())
                        if nextParent.elemType == 'para':
                            visitParents = False
                    except IndexError:
                        visitParents = False
            return res
        if parent.tagsToClose and \
            (parent.tagsToClose[-1].elemType == 'para') and \
            (self.elem in NOT_INSIDE_P):
            return (parent.tagsToClose[-1].setConflictual(),)
        # Check elements that can't be found within a list
        if (parent.elemType == 'list') and (self.elem in NOT_INSIDE_LIST):
            return (parent.setConflictual(),)
        return ()

    def addInnerParagraph(self, env):
        '''Dump an inner paragraph inside self (if not already done)'''
        if self.tagsToClose: return # We already did it
        dump = env.dumpString
        dump('<text:p')
        # Apply element's inner style if defined
        if self.innerStyle and not self.innerAttributes:
            dump(' text:style-name="%s"' % self.innerStyle)
        elif self.elem == 'li':
            itemStyle = env.getCurrentElement(isList=True).elem # ul or ol
            # Which 'li'-related style must I use ?
            if self.classAttr:
                odtStyle = env.parser.caller.findStyle(self,
                  classValue=self.classAttr)
                if odtStyle and (odtStyle.name == 'podItemKeepWithNext'):
                    itemStyle += '_kwn'
                styleName = env.itemStyles[itemStyle]
                env.dumpString(' text:style-name="%s"' % styleName)
            else:
                # Check if a style must be applied on 'p' tags
                toDump = env.getOdfAttributes(self.protos['p'],
                                              attrs=self.innerAttributes)
                if not toDump:
                    toDump = ' text:style-name="%s"' % env.itemStyles[itemStyle]
                env.dumpString(toDump)
        else:
            # Check if a style must be applied on 'p' tags
            env.dumpString(env.getOdfAttributes(self.protos['p'],
                                                self.innerAttributes))
        env.dumpString('>')
        self.tagsToClose.append(HtmlElement('p', {}))

    def addInnerAttributes(self, attrs):
        '''p_attrs are attributes parsed from the removed sub-tag'''
        if self.innerAttributes: return # Already done
        if attrs.has_key('class') or attrs.has_key('style'):
            self.innerAttributes = attrs

    def dump(self, start, env):
        '''Dumps the start or end (depending on p_start) tag of this HTML
           element. We must take care of potential innerTags.'''
        # Compute the tag in itself
        tag = ''
        prefix = '<'
        if not start: prefix += '/'
        # Compute tag attributes
        attrs = ''
        if start:
            if self.elemType == 'list':
                # I must specify the list style
                attrs += ' %s:style-name="%s"' % (env.textNs, self.odStyle)
                if self.elem == 'ol':
                    # I have interrupted a numbered list. I need to continue
                    # the numbering.
                    attrs += ' %s:continue-numbering="true"' % env.textNs
            else:
                attrs = env.getOdfAttributes(self)
        tag = prefix + self.getOdfTag(env) + attrs + '>'
        # Close/open subTags if any
        for subElem in self.tagsToClose:
            subTag = subElem.dump(start, env)
            if start: tag += subTag
            else: tag = subTag + tag
        return tag

    def __repr__(self):
        return '<Html "%s">' % self.elem

# Create protypical instances
for tag in ('p', 'ul', 'ol'): HtmlElement.protos[tag] = HtmlElement(tag, {})

# ------------------------------------------------------------------------------
class HtmlTable:
    '''Represents an HTML table, and also a sub-buffer. When parsing elements
       corresponding to an HTML table (<table>, <tr>, <td>, etc), we can't dump
       corresponding ODF elements directly into the global result buffer
       (XhtmlEnvironment.res). Indeed, when dumping an ODF table, we must
       dump columns declarations at the beginning of the table. So before
       dumping rows and cells, we must know how much columns will be present
       in the table. It means that we must first parse the first <tr> entirely
       in order to know how much columns are present in the HTML table before
       dumping the ODF table. So we use this class as a sub-buffer that will
       be constructed as we parse the HTML table; when encountering the end
       of the HTML table, we will dump the result of this sub-buffer into
       the parent buffer, which may be the global buffer or another table
       buffer.'''
    def __init__(self, env, attrs):
        self.env = env
        self.elem = 'table'
        self.removeTag = False
        self.contentDumped = self.contentDumpedOrSub = False
        self.name = env.getUniqueStyleName('table')
        self.styleNs = env.ns[OdfEnvironment.NS_STYLE]
        self.tableNs = env.ns[OdfEnvironment.NS_TABLE]
        # If an attribute "border=0" is defined in p_attrs, we store it here
        self.border = not attrs.has_key('border') or (attrs['border'] == '1')
        # If a CSS property "border-spacing" is defined on this table,
        # m_setTableStyle will parse it and store it here.
        self.borderSpacing = None
        # Get the TableProperties instance. There is always one.
        self.props = env.parser.caller.findStyle(self, attrs)
        self.style, self.widthInPx = self.setTableStyle(attrs, env)
        self.res = u'' # The sub-buffer
        self.tempRes = u'' # The temporary sub-buffer, into which we will
        # dump all table sub-elements, until we encounter the end of the first
        # row. Then, we will know how much columns are defined in the table;
        # we will dump columns declarations into self.res and dump self.tempRes
        # into self.res.
        self.firstRowParsed = False # Was the first table row completely parsed?
        self.nbOfColumns = 0
        # Are we currently within a table cell? Instead of a boolean, the field
        # stores an integer. The integer is > 1 if the cell spans more than one
        # column.
        self.inCell = 0
        # The index, within the current row, of the current cell
        self.cellIndex = -1
        # The size of the content of the currently parsed table cell
        self.cellContentSize = 0
        # The size of the longest word of the currently parsed table cell
        self.cellLongestWord = 0
        # The following lists store, for every column: the size of (a) the
        # longest content and (b) the longest words of all its cells.
        self.columnContentSizes = []
        self.columnLongestWords = [] # Computed but currently not used
        # The following list stores, for every column, its width, if specified.
        # If widths are found, self.columnContentSizes will not be used:
        # self.columnWidths will be used instead.
        self.columnWidths = []

    def setTableStyle(self, attrs, env):
        '''The default ODT style "podTable" will apply to the table, excepted if
           a specific table width is specified. In this case, we will create a
           dynamic style whose parent will be "podTable". This method returns a
           tuple (styleName, tableWidhPx). The table width in pixels is
           sometimes needed to convert column widths, expressed in pixels, to
           percentages.'''
        tableProps = self.props
        cssStyles = CssStyles('table', attrs)
        if hasattr(cssStyles, 'borderspacing'):
            # This attribute will be used at the cell level. Extract it and
            # delete it.
            self.borderSpacing = cssStyles.borderspacing
            del cssStyles.borderspacing
        # Get the table width and alignment. Is there a width defined for this
        # table in p_attrs?
        hasWidth = hasattr(cssStyles, 'width')
        width = tableProps.getWidth(cssStyles)
        align = getattr(cssStyles, 'textalign', 'left')
        # Get the page width, in cm, and the ratio "px2cm"
        pageWidth, px2cmRatio = tableProps.pageWidth, tableProps.px2cm
        if pageWidth == None:
            pageWidth = self.env.renderer.stylesManager.pageLayout.getWidth()
        if px2cmRatio == None:
            px2cmRatio = px2cm
        # Compute the table attributes for setting its width
        s = self.styleNs
        if width.unit == '%':
            tableWidth = pageWidth * (width.value / 100.0)
            percentage = str(width.value)
        else: # cm or px
            ratio = (width.unit == 'cm') and 1.0 or px2cmRatio
            tableWidth = min(float(width.value) / ratio, pageWidth)
            percentage = formatNumber(float(tableWidth/pageWidth)*100, sep='.')
        # Compute the table size in PX: it will be needed to convert column
        # widths in px to percentages.
        tableWidthPx = int(tableWidth * px2cmRatio)
        # Do not define a specific table style if no table width was specified
        if not hasWidth: return 'podTable', tableWidthPx
        # Create the style for setting a width to this table and return its name
        decl = '<%s:style %s:name="%s" %s:family="table" ' \
               '%s:parent-style-name="podTable"><%s:table-properties ' \
               '%s:width="%scm" %s:rel-width="%s%%" %s:table-align="%s" ' \
               '%s:align="%s"/></%s:style>' % \
               (s, s, self.name, s, s, s, s, formatNumber(tableWidth, sep='.'),
                s, percentage, self.tableNs, align, self.tableNs, align, s)
        env.renderer.dynamicStyles['content'].append(decl.encode('utf-8'))
        return self.name, tableWidthPx

    def setColumnWidth(self, width):
        '''A p_width is defined for the current cell. Store it in
           self.columnWidths'''
        # But first, ensure self.columnWidths is long enough
        widths = self.columnWidths
        while (len(widths)-1) < self.cellIndex: widths.append(None)
        # The first encountered value will be kept
        if widths[self.cellIndex] == None:
            widths[self.cellIndex] = width

    def computeColumnStyles(self, renderer):
        '''Once the table has been completely parsed, self.columnContentSizes
           should be correctly filled. Based on this, we can deduce the width
           of every column and create the corresponding style declarations, in
           p_renderer.dynamicStyles.'''
        # The objective is to compute, in "widths", relative column widths,
        # as percentages, from 0 to 1.0.
        widths = []
        i = 0
        # Compute the min and max column sizes, as percentages
        minCellWidth = min(1.0/(self.nbOfColumns*2), self.props.minColumnWidth)
        maxCellWidth = 1 - minCellWidth
        # 1st step: collect or compute widths for columns for which a width has
        # been specified.
        remainingPc = 1.0 # What global percentage will remain after this step ?
        noWidth = 0 # Count the number of columns with no specified width
        while i < self.nbOfColumns:
            if (i < len(self.columnWidths)) and self.columnWidths[i]:
                width = self.columnWidths[i]
                if width.unit == 'px': 
                    widthAsPc = float(width.value) / self.widthInPx
                elif width.unit == '%':
                    widthAsPc = float(width.value) / 100
                else:
                    # "cm" or "pt". Ignore this for the moment.
                    widthAsPc = None
                # Ignore the computed width if wrong
                if (widthAsPc <= minCellWidth) or (widthAsPc >= maxCellWidth):
                    # A cell width of 1.0 (=100%) must be ignored: if there is a
                    # single cell, it is implicit; if there are more cells, it
                    # means that others cells will have a width of 0% and will
                    # be invisible.
                    widthAsPc = None
                widths.append(widthAsPc)
                if widthAsPc:
                    remainingPc -= widthAsPc
                else:
                    noWidth += 1
            else:
                widths.append(None)
                noWidth += 1
            i += 1
        # We must guarantee that at least 5% are available for every column
        # having no percentage yet. Else, they could be invisible. If it is not
        # the case, reset all column widths.
        if noWidth:
            required = minCellWidth * noWidth
            if remainingPc < required:
                widths = [None] * len(widths)
                remainingPc = 1.0
        # 2nd step: compute widths of columns for which no width has been
        # specified, by using self.columnContentSizes and
        # self.columnLongestWords. As a preamble, compute the total size of
        # content from all columns.
        contentTotal = 0
        i = 0
        contentSizes = self.columnContentSizes
        longestWords = self.columnLongestWords
        while i < self.nbOfColumns:
            # Ignore columns for which a width has already been computed
            if widths[i] == None:
                if (i < len(contentSizes)) and contentSizes[i]:
                    contentTotal += contentSizes[i]
            i += 1
        # We will first store, in "widths", a tuple (f_width, b_minForced)
        # instead of a f_width directly. Indeed, we must ensure that every such
        # width is >= minCellWidth. All cells with a width below it will be
        # flagged with p_minForced=True. And in a second step, the surplus
        # granted to those cells will be deduced from the others.
        i = 0
        surplus = 0.0 # The total surplus granted to too narrow cells
        remainingCount = 0 # The number of cells with no surplus
        while i < self.nbOfColumns:
            if widths[i] == None:
                # Get the content size and longest word for this column
                if (i < len(contentSizes)) and contentSizes[i]:
                    contentSize = contentSizes[i]
                    longest = longestWords[i]
                else:
                    contentSize = longest = 0
                # Compute the column width
                width = (float(contentSize) / contentTotal) * remainingPc
                if width < minCellWidth:
                    surplus += minCellWidth - width
                    val = (minCellWidth, True)
                else:
                    remainingCount += 1
                    val = (width, False)
                widths[i] = val
            i += 1
        # "Convert" stored tuples into final values
        i = 0
        while i < self.nbOfColumns:
            if isinstance(widths[i], tuple):
                if not surplus:
                    # Simply store the value without changing it
                    widths[i] = widths[i][0]
                else:
                    if widths[i][1]:
                        # Simply store the forced minimum
                        widths[i] = widths[i][0]
                    else:
                        # Reduce this value by a part of the surplus
                        widths[i] = widths[i][0] - (surplus / remainingCount)
            i += 1
        # Multiply widths (as percentages) by a predefined number, in order to
        # get a LibreOffice-compliant column width.
        i = 0
        total = 65534.0
        while i < self.nbOfColumns:
            widths[i] = int(widths[i] * total)
            i += 1
        # Compute style declaration corresponding to every column
        s = self.styleNs
        i = 0
        for width in widths:
            i += 1
            # Compute the width of this column, relative to "total"
            decl = '<%s:style %s:name="%s.%d" %s:family="table-column">' \
                   '<%s:table-column-properties %s:rel-column-width="%d*"' \
                   '/></%s:style>' % (s, s, self.name, i, s, s, s, width, s)
            renderer.dynamicStyles['content'].append(decl.encode('utf-8'))

# ------------------------------------------------------------------------------
class XhtmlEnvironment(XmlEnvironment):
    itemStyles = {'ul': 'podBulletItem', 'ol': 'podNumberItem',
                  'ul_kwn': 'podBulletItemKeepWithNext',
                  'ol_kwn': 'podNumberItemKeepWithNext'}
    defaultListStyles = {'ul': 'podBulletedList', 'ol': 'podNumberedList'}
    # For list styles, this dict maps values of HTML attrbute "type" to CSS
    # property values for attibute "list-style-type".
    typeToListStyleType = {'1': 'decimal', 'a': 'lower-alpha',
      'A': 'upper-alpha', 'i': 'lower-roman', 'I': 'upper-roman'}
    # Mapping between HTML list styles and ODT list styles
    listClasses = {'ol': NumberedProperties, 'ul': BulletedProperties}
    # "list-style-type" values supported by OpenDocument
    listFormats = {
      # Number formats
      'lower-alpha': ('a',), 'upper-alpha': ('A',), 'lower-latin': ('a',),
      'upper-latin': ('A',), 'lower-roman': ('i',), 'upper-roman': ('I',),
      'decimal': ('1',),
      # Bullet formats
      'disc': (u'•'), 'circle': (u'◦'), 'square': (u'▪'), 'none': ''}

    def __init__(self, renderer):
        XmlEnvironment.__init__(self)
        self.renderer = renderer
        self.ns = renderer.currentParser.env.namespaces
        self.res = u''
        self.currentContent = u''
        self.currentElements = [] # Stack of currently walked elements
        self.currentLists = [] # Stack of currently walked lists (ul or ol)
        self.currentTables = [] # Stack of currently walked tables
        self.lastElem = None # Last walked element before the current one
        self.textNs = self.ns[OdfEnvironment.NS_TEXT]
        self.linkNs = self.ns[OdfEnvironment.NS_XLINK]
        self.tableNs = self.ns[OdfEnvironment.NS_TABLE]
        self.styleNs = self.ns[OdfEnvironment.NS_STYLE]
        # The following attr will be True when parsing parts of the XHTML that
        # must be ignored.
        self.ignore = False
        # Maintain a dict of collected [Bulleted|Numbered]Properties
        # instances, to avoid generating the corresponding list styles several
        # times.
        self.listProperties = {}

    def getUniqueStyleName(self, type):
        '''Gets a unique name for an element of some p_type (a table, a
           list).'''
        elems = str(time.time()).split('.')
        return '%s%s%s%d' % (type.capitalize(), elems[0], elems[1],
                             random.randint(1,100))

    def getCurrentElement(self, isList=False):
        '''Gets the element that is on the top of self.currentElements or
           self.currentLists.'''
        res = None
        if isList:
            elements = self.currentLists # Stack of list elements only
        else:
            elements = self.currentElements # Stack of all elements (including
            # elements also pushed on other stacks, like lists and tables).
        if elements:
            res = elements[-1]
            if res.removeTag:
                # This tag will not be dumped: the real current one is the
                # parent.
                res = res.parent
        return res

    def anElementIsMissing(self, previousElem, currentElem):
        return previousElem and (previousElem.elem in OUTER_TAGS) and \
               ((not currentElem) or (currentElem.elem in INNER_TAGS))

    def dumpCurrentContent(self, place, elem):
        '''Dumps content that was temporarily stored in self.currentContent
           into the result.'''
        currentElem = self.getCurrentElement()
        # Remove the trailing whitespace if needed
        if place == 'start':
            if self.currentContent.endswith(' ') and \
               ((elem not in INNER_TAGS) or (elem == 'br')):
                self.currentContent = self.currentContent[:-1]
        # Remove the leading whitespace if needed
        if self.currentContent.startswith(' '):
            last = self.lastElem
            if (place == 'end') and (elem in INNER_TAGS):
                parent = currentElem.parent
                if not parent or not parent.contentDumpedOrSub or (last=='br'):
                    self.currentContent = self.currentContent[1:]
            else:
                if not last or (last not in INNER_TAGS_NO_BR):
                    self.currentContent = self.currentContent[1:]
        if self.currentContent:
            # Manage missing elements
            if self.anElementIsMissing(currentElem, None):
                currentElem.addInnerParagraph(self)
            # Dump the current content
            self.dumpString(escapeXml(self.currentContent))
            self.currentElements[-1].contentDumped = True
            for e in self.currentElements:
                e.contentDumpedOrSub = True
        # Reinitialise the current content
        if self.currentContent:
            # If we are within a table cell, update the total size of cell
            # content and the longest found word.
            if self.currentTables and self.currentTables[-1].inCell:
                contentSize = len(self.currentContent)
                longest = 0 # Longest word's size
                # "longest" is currently not used. We do not compute it to save
                # processing.
                # for word in self.currentContent.split():
                #    longest = max(longest, len(word))
                for table in self.currentTables:
                    table.cellContentSize += contentSize
                    table.cellLongestWord = max(table.cellLongestWord, longest)
            self.currentContent = u''

    def getOdfAttributes(self, xhtmlElem, attrs=None):
        '''Gets the ODF attributes to dump for p_xhtmlElem. p_attrs are the
           parsed attributes from the p_xhtmlElem.'''
        # Complete attributes if inherited from a parent tag
        if xhtmlElem.elem in ('td', 'th'):
            table = self.currentTables[-1]
            border = table.border
            if not border:
                attrs = addPair('border', '0', attrs)
            spacing = table.borderSpacing
            if spacing:
                attrs = addPair('cellspacing', spacing, attrs)
        # Get the base ODF style for this p_xhtmlElem
        style = self.parser.caller.findStyle(xhtmlElem, attrs)
        if style: return style.getOdfAttributes(attrs)
        return ''

    def addListProperties(self, elem, listProps):
        '''Ensures the ListProperties instance p_listProps is among
           self.listProperties.'''
        for name, value in self.listProperties.iteritems():
            if value == listProps:
                return name
        # If we are here, p_listProps wat not found. Add it.
        name = self.getUniqueStyleName('list')
        self.listProperties[name] = listProps
        return name

    def addListPropertiesByName(self, elem, name):
        '''A specific list style must be used, based on HTML attribute "type" or
           CSS property "list-style-type". Add the corresponding
           BulletedProperties or NumberedProperties instance in
           self.listProperties if not present yet.'''
        if name in self.listProperties: return
        # Determine the ListProperties class to use
        klass = self.listClasses[elem]
        # Determine the format of bullets/numbers
        formats = (name in self.listFormats) and self.listFormats[name] or \
                  klass.defaultFormats
        # Create the Properties instance
        styleName = 'L-%s' % name
        self.listProperties[styleName] = klass(formats=formats)
        return styleName

    def getListStyle(self, elem, attrs):
        '''Gets the list style to apply to p_elem (a "ol" or "ul"). If no
           specific style information is found in p_attrs, a default style is
           applied, from XhtmlEnvironment.defaultListStyles. Else, a specific
           list style is created and added to dynamic styles.'''
        # Check if a specific style must be created
        res = None
        # Check first in the styles mappings
        listProps= self.parser.caller.findStyle(HtmlElement.protos[elem], attrs)
        if listProps:
            # I have a ListProperties instance from a styles mapping. Get a name
            # for the corresponding style.
            return self.addListProperties(elem, listProps)
        # Check CSS attribute "list-style-type"
        styles = CssStyles(elem, attrs)
        if hasattr(styles, 'liststyletype'):
            typeValue = styles.liststyletype.value
            if typeValue not in ('initial', 'inherit'):
                res = typeValue
        # Check HTML attribute "type"
        if not res and attrs.has_key('type'):
            res = self.typeToListStyleType[attrs['type']]
        if res:
            # A specific style has been found. Ensure it will be added among
            # dynamic styles.
            res = self.addListPropertiesByName(elem, res)
        else:
            # Apply a default style, added by default among dynamic styles
            res = self.defaultListStyles[elem]
        return res

    def getTags(self, elems, start=True, ignoreToRemove=False):
        '''This method returns a series of start or end tags (depending on
           p_start) that correspond to HtmlElement instances in p_elems.'''
        res = ''
        for elem in elems:
            # Ignore tags flagged "to remove"
            if ignoreToRemove and elem.removeTag: continue
            tag = elem.dump(start, self)
            if start: res += tag
            else: res = tag + res
        return res

    def closeConflictualElements(self, conflictElems):
        '''This method dumps end tags for p_conflictElems, excepted if those
           tags would be empty. In this latter case, tags are purely removed
           from the result.'''
        startTags = self.getTags(conflictElems, start=True, ignoreToRemove=True)
        if startTags and self.res.endswith(startTags):
            # In this case I would dump an empty (series of) tag(s). Instead, I
            # will remove those tags.
            self.res = self.res[:-len(startTags)]
        else:
            tags = self.getTags(conflictElems, start=False, ignoreToRemove=True)
            self.dumpString(tags)

    def dumpString(self, s):
        '''Dumps arbitrary content p_s.
           If the table stack is not empty, we must dump p_s into the buffer
           corresponding to the last parsed table. Else, we must dump p_s
           into the global buffer (self.res).'''
        if self.currentTables:
            currentTable = self.currentTables[-1]
            if (not currentTable.res) or currentTable.firstRowParsed:
                currentTable.res += s
            else:
                currentTable.tempRes += s
        else:
            self.res += s

    def getTagsToReopen(self, conflictElems):
        '''Normally, tags to reopen are equal to p_conflictElems. But we have a
           special case. Indeed, if a conflict elem has itself tagsToClose,
           the last tag to close may not be needed anymore on the tag to
           reopen, so we remove it.'''
        conflictElems[-1].tagsToClose = []
        return conflictElems

    def onElementStart(self, elem, attrs):
        '''Returns an HtmlElement instance representing the currently walked
           p_elem.'''
        self.dumpCurrentContent('start', elem)
        previousElem = self.getCurrentElement()
        currentElem = HtmlElement(elem, attrs, parent=previousElem)
        # Manage conflictual elements
        conflictElems = currentElem.getConflictualElements(self, attrs)
        if conflictElems:
            # We must close the conflictual elements, and once the currentElem
            # will be dumped, we will re-open the conflictual elements.
            self.closeConflictualElements(conflictElems)
            currentElem.tagsToReopen = self.getTagsToReopen(conflictElems)
        # Manage missing elements
        if self.anElementIsMissing(previousElem, currentElem):
            previousElem.addInnerParagraph(self)
        # Add the current element on the stack of walked elements
        self.currentElements.append(currentElem)
        if elem in XHTML_LISTS:
            # Update stack of current lists
            self.currentLists.append(currentElem)
        elif elem == 'table':
            # Update stack of current tables
            self.currentTables.append(HtmlTable(self, attrs))
        elif elem in TABLE_COL_TAGS:
            # Determine colspan
            colspan = 1
            if attrs.has_key('colspan'): colspan = int(attrs['colspan'])
            table = self.currentTables[-1]
            table.inCell = colspan
            table.cellIndex += colspan
            # If we are in the first row of a table, update columns count
            if not table.firstRowParsed:
                table.nbOfColumns += colspan
            styles = CssStyles(elem, attrs)
            if hasattr(styles, 'width') and (colspan == 1):
                table.setColumnWidth(styles.width)
        return currentElem

    def onElementEnd(self, elem):
        res = None
        self.dumpCurrentContent('end', elem)
        currentElem = self.currentElements.pop()
        toDump = None
        if elem in XHTML_LISTS:
            self.currentLists.pop()
        elif elem == 'table':
            table = self.currentTables.pop()
            if table.nbOfColumns:
                # Computes the column styles required by the table
                table.computeColumnStyles(self.parser.caller.renderer)
            # Dumps the content of the last parsed table into the parent buffer
            self.dumpString(table.res)
        elif elem in TABLE_ROW_TAGS:
            table = self.currentTables[-1]
            table.cellIndex = -1
            if not table.firstRowParsed:
                table.firstRowParsed = True
                # First row is parsed. I know the number of columns in the
                # table: I can dump the columns declarations.
                for i in range(1, table.nbOfColumns + 1):
                    table.res+= '<%s:table-column %s:style-name="%s.%d"/>' % \
                                (self.tableNs, self.tableNs, table.name, i)
                table.res += table.tempRes
                table.tempRes = u''
        elif elem in TABLE_COL_TAGS:
            table = self.currentTables[-1]
            # If we are walking a td or th, update "columnContentSizes" and
            # "columnLongestWords" for the currently parsed table, excepted if
            # the cell spans several columns.
            if elem != 'col':
                # Divide the content size if cell colspan > 1
                cellContentSize = table.cellContentSize / table.inCell
                cellLongestWord = table.cellLongestWord / table.inCell
                i = table.cellIndex
                sizes = table.columnContentSizes
                wordSizes = table.columnLongestWords
                # Insert None values if the lists are too small
                while (len(sizes)-1) < i:
                    sizes.append(None)
                    wordSizes.append(None)
                longest = max(sizes[i], cellContentSize, 5)
                wordLongest = max(wordSizes[i], cellLongestWord, 5)
                # Put a maximum
                sizes[i] = min(longest, 100)
                wordSizes[i] = min(wordLongest, 25)
            table.inCell = table.cellContentSize = table.cellLongestWord = 0
        elif elem in STYLED_INNER_TAGS:
            parent = self.currentElements and self.currentElements[-1] or None
            if parent and (parent.elem in STYLED_INNER_TAGS) and \
               not parent.contentDumped:
                # LibreOffice does not support multiple inner tags surrounding
                # the same text. If we have the case in XHTML (ie,
                # <u><b>Text</b></u>), we should generate a single <text:span>
                # whose style defines a combination of bold and underline. We
                # don't implement that. Instead, we will include in the result
                # an invisible char that will artificially produce different
                # texts for the inner tags. <b><u>Text</u></b> will then be
                # converted to (pseudo-odf)
                #      <span_b><span_u>Text</span_u>[[I]]</span_b>
                # [[I]] being the invisible char, named "Zero-width space", a
                # standard unicode character.
                toDump = u"\u200B"
        if currentElem.tagsToClose:
            self.closeConflictualElements(currentElem.tagsToClose)
        if currentElem.tagsToReopen:
            res = currentElem.tagsToReopen
        self.lastElem = currentElem.elem
        return currentElem, res, toDump

# ------------------------------------------------------------------------------
class XhtmlParser(XmlParser):
    def lowerizeInput(self, elem, attrs=None):
        '''Because (X)HTML is case insensitive, we may receive input p_elem and
           p_attrs in lower-, upper- or mixed-case. So here we produce lowercase
           versions that will be used throughout our parser.'''
        resElem = elem.lower()
        resAttrs = attrs
        if attrs:
            resAttrs = {}
            for attrName in attrs.keys():
                resAttrs[attrName.lower()] = attrs[attrName]
        if attrs == None:
            return resElem
        else:
            return resElem, resAttrs

    def startElement(self, elem, attrs):
        elem, attrs = self.lowerizeInput(elem, attrs)
        e = XmlParser.startElement(self, elem, attrs)
        currentElem = e.onElementStart(elem, attrs)
        if currentElem.removeTag: # Do not dump the start tag
            if currentElem.parent.contentDumpedOrSub:
                # Dump a line break instead, only if content was already dumped
                # into the parent.
                e.dumpString('<text:line-break/>')
            return
        odfTag = currentElem.getOdfTag(e)

        if elem in HTML_2_ODT:
            e.dumpString('<' + odfTag)
            e.dumpString(e.getOdfAttributes(currentElem, attrs))
            e.dumpString('>')
        elif elem == 'a':
            e.dumpString('<%s %s:type="simple"' % (odfTag, e.linkNs))
            if attrs.has_key('href'):
                e.dumpString(' %s:href="%s"' % (e.linkNs,
                                                escapeXml(attrs['href'])))
            e.dumpString('>')
        elif elem in XHTML_LISTS:
            prologue = ''
            if len(e.currentLists) >= 2:
                # It is a list into another list. In this case the inner list
                # must be surrounded by a list-item element.
                prologue = '<%s:list-item>' % e.textNs
            numbering = ''
            if elem == 'ol':
                numbering = ' %s:continue-numbering="false"' % e.textNs
            currentElem.odStyle = e.getListStyle(elem, attrs)
            e.dumpString('%s<%s %s:style-name="%s"%s>' % (
              prologue, odfTag, e.textNs, currentElem.odStyle, numbering))
        elif elem == 'li':
            # Must numbering restart at this "li" ?
            attrs = e.currentLists[-1].attrs
            restart = ''
            if attrs and ('start' in attrs):
                restart = ' %s:start-value="%d"' % (e.textNs, attrs['start'])
                del attrs['start']
            e.dumpString('<%s%s>' % (odfTag, restart))
        elif elem in ('thead', 'tr'):
            e.dumpString('<%s>' % odfTag)
        elif elem == 'table':
            # Here we must call "dumpString" only once
            table = e.currentTables[-1]
            e.dumpString('<%s %s:name="%s" %s:style-name="%s">' % \
                         (odfTag,e.tableNs,table.name,e.tableNs,table.style))
        elif elem == 'img':
            style = None
            if attrs.has_key('style'): style = attrs['style']
            imgCode = e.renderer.importDocument(at=attrs['src'],
              wrapInPara=False, style=style, format='image')
            e.dumpString(imgCode)
        elif elem in IGNORABLE_TAGS:
            e.ignore = True

    def endElement(self, elem):
        elem = self.lowerizeInput(elem)
        e = XmlParser.endElement(self, elem)
        currentElem, elemsToReopen, toDump = e.onElementEnd(elem)
        # Determine the tag to dump
        startTag, endTag = currentElem.getOdfTags(e)
        if currentElem.isConflictual:
            # Compute the start tag, with potential styles applied
            startTag = e.getTags((currentElem,), start=True)
        if currentElem.isConflictual and e.res.endswith(startTag):
            # We will not dump it, it would constitute a silly empty tag
            e.res = e.res[:-len(startTag)]
        else:
            # Dump the end tag, but dump some additional stuff if required
            if elem in XHTML_LISTS:
                if len(e.currentLists) >= 1:
                    # We were in an inner list. So we must close the list-item
                    # tag that surrounds it.
                    endTag = '%s</%s:list-item>' % (endTag, e.textNs)
            if endTag and not currentElem.removeTag:
                e.dumpString(endTag)
        if elem in IGNORABLE_TAGS:
            e.ignore = False
        if toDump:
            # We have some char(s) to dump into the result after the end tag
            e.dumpString(toDump)
        if elemsToReopen:
            e.dumpString(e.getTags(elemsToReopen, start=True))

    def characters(self, content):
        e = XmlParser.characters(self, content)
        if e.ignore: return
        e.currentContent += WhitespaceCruncher.crunch(content, e.currentContent)

    def endDocument(self):
        '''Dump all collected list styles'''
        ds = self.caller.renderer.dynamicStyles['styles']
        env = self.env
        ns = {'text': env.textNs, 'style': env.styleNs}
        for name, props in env.listProperties.iteritems():
            ds.append(props.dumpStyle(name, ns))

# ------------------------------------------------------------------------------
class Xhtml2OdtConverter:
    '''Converts a chunk of XHTML into a chunk of ODT'''
    def __init__(self, xhtmlString, encoding, stylesManager, localStylesMapping,
                 keepWithNext, renderer):
        self.renderer = renderer
        self.xhtmlString = xhtmlString
        self.encoding = encoding # Todo: manage encoding that is not utf-8
        self.stylesManager = stylesManager
        self.localStylesMapping = localStylesMapping
        self.odtChunk = None
        self.xhtmlParser = XhtmlParser(XhtmlEnvironment(renderer), self)
        if keepWithNext: self.xhtmlString = self.applyKeepWithNext()

    def run(self):
        self.xhtmlParser.parse(self.xhtmlString)
        return self.xhtmlParser.env.res

    def applyKeepWithNext(self):
        '''This method is called prior to parsing self.xhtmlString in order to
           add specific CSS classes to some XHTML tags, implementing the
           "keep-with-next" functionality. If the last tag is:
           * a paragraph (tag "p"), class "ParaKWN" will be set;
           * a bullet (tag "li"), class "podItemKeepWithNext" will be set.

           Note that this latter class will then be converted by the XHTML
           parser into "real" style "podBulletItemKeepWithNext" or
           "podNumberItemKeepWithNext", if the "li" is, respectively, in a "ul"
           or "ol" tag.
        '''
        res = self.xhtmlString
        lastParaIndex = res.rfind('<p')
        lastItemIndex = res.rfind('<li')
        if (lastParaIndex != -1) or (lastItemIndex != -1):
            # Is the last one a paragraph or an item ?
            if lastParaIndex > lastItemIndex:
                # A paragraph
                styleName = 'ParaKWN'
                elemLenght = 2
            else:
                # An item
                styleName = 'podItemKeepWithNext'
                elemLenght = 3
            maxIndex = max(lastParaIndex, lastItemIndex)
            # Does this element already have a "class" attribute ?
            if res.find('class="', maxIndex) == -1:
                # No: I add the style
                res = res[:maxIndex+elemLenght] + (' class="%s" ' % styleName) \
                      + res[maxIndex+elemLenght:]
        return res

    def findStyle(self, elem, attrs=None, classValue=None):
        return self.stylesManager.findStyle(elem, attrs, classValue,
                                            self.localStylesMapping)
# ------------------------------------------------------------------------------
