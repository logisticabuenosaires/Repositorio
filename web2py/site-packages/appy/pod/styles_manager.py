# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
# Appy is a framework for building applications in the Python language.
# Copyright (C) 2007 Gaetan Delannay

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,USA.

# ------------------------------------------------------------------------------
import re, os.path
from UserDict import UserDict
from appy.pod import *
from appy.pod.odf_parser import OdfEnvironment, OdfParser
from appy.pod.doc_importers import px2cm as px2cmRatio
from appy.shared.css import parseStyleAttribute, CssStyles, CssValue
from appy.shared.utils import getElementAt, formatNumber

# Possible states for the parser
READING = 0 # Default state
PARSING_STYLE = 1 # Parsing a style definition
PARSING_MASTER_STYLES = 2 # Parsing section "master-styles"
PARSING_PAGE_LAYOUT = 3 # Parsing a page layout

# Error-related constants ------------------------------------------------------
MAPPING_NOT_DICT = 'The styles mapping must be a dictionary or a UserDict ' \
  'instance.'
MAPPING_KEY_NOT_STRING = "The styles mapping dictionary's keys must be strings."
MAPPING_ELEM_NOT_STRING = 'The styles mapping value for key "%s" must be a ' \
  'string.'
MAPPING_ELEM_EMPTY = 'In your styles mapping, you inserted an empty key ' \
  'and/or value.'
MAPPING_WRONG_VALUE_TYPE = 'For key "%s", the value must be of type "%s".'
UNSTYLABLE_TAG = 'You can\'t associate a style to element "%s". Unstylable ' \
  'elements are: %s'
STYLE_NOT_FOUND = 'OpenDocument style "%s" was not found in your template. ' \
  'Note that the styles names ("Heading 1", "Standard"...) that appear when ' \
  'opening your template with OpenOffice, for example, are a super-set of ' \
  'the styles that are really recorded into your document. Indeed, only ' \
  'styles that are in use within your template are actually recorded into ' \
  'the document. You may consult the list of available styles ' \
  'programmatically by calling your pod renderer\'s "getStyles" method.'
HTML_PARA_ODT_TEXT = 'For XHTML element "%s", you must associate a ' \
  'paragraph-wide OpenDocument style. "%s" is a "text" style (that applies ' \
  'to only a chunk of text within a paragraph).'
HTML_TEXT_ODT_PARA = 'For XHTML element "%s", you must associate an ' \
  'OpenDocument "text" style (that applies to only a chunk of text within a ' \
  'paragraph). "%s" is a paragraph-wide style.'

# ------------------------------------------------------------------------------
class TableProperties:
    '''In a styles mapping, the value @key "table" must be an instance of this
       class.'''
    def __init__(self, pageWidth=None, px2cm=px2cmRatio, wideAbove=495,
                 minColumnWidth=0.07):
        # pod computes, in cm, the width of the master page for a pod template.
        # Table widths expressed as percentages will be based on it. But if your
        # XHTML table(s) lie(s) within a section that has a specific page style
        # with another width, specify it here (as a float value, in cm).
        self.pageWidth = pageWidth
        # Table widths expressed as pixels will use a "pixels to cm" ratio as
        # defined in appy.pod.doc_importers.px2cm. If this is wrong for you,
        # specify another ratio here. The width in cm will be computed as:
        #             (table width in pixels) / px2cm
        self.px2cm = px2cm
        # Every table with no specified width will be "wide" (=100% width).
        # If a table width is specified in px and is above the value defined
        # here, it will be forced to 100%.
        self.wideAbove = wideAbove
        # pod ensures that every column will at least get a minimum width
        # (expressed as a percentage: a float value between 0.0 and 1.0). You
        # can change this minimum here.
        self.minColumnWidth = minColumnWidth

    def getWidth(self, attrs):
        '''Return the table width as a appy.shared.css.CssValue instance.
           p_attrs is a CssStyles instance containing parsed table
           attributes.'''
        if not hasattr(attrs, 'width'): return CssValue('width', '100%')
        width = attrs.width
        if (self.wideAbove != None) and (width.unit == 'px') and \
           (width.value > self.wideAbove):
            return CssValue('width', '100%')
        return width

class ListProperties:
    '''Base abstract class for defining properties of a XHTML list'''
    def __init__(self, levels, formats, delta, space):
        # The number of indentation levels supported
        self.levels = levels
        # The list of formats for bullets/numbers
        self.formats = formats
        # The number of inches to increment at each level (as a float)
        self.delta = delta
        # The space, in inches (as a float), between the bullet/number and the
        # text.
        self.space = space
        # The number of levels can > or < to the number of formats. In those
        # cases, formats will be applied partially or cyclically to levels.

    def dumpStyle(self, name, ns):
        '''Returns the OpenDocument style definition corresponding to this
           instance.'''
        nsText = ns['text']
        nsStyle = ns['style']
        res = []
        spaceBefore = 0
        space = formatNumber(self.space, sep='.', removeTrailingZeros=True)
        for i in range(self.levels):
            spaceBefore += self.delta
            sb = formatNumber(spaceBefore, sep='.', removeTrailingZeros=True)
            level = u'  <%s:list-level-style-%s %s:level="%d" ' \
              '%s:style-name="%s" %s>\n    <%s:list-level-properties ' \
              '%s:space-before="%sin" %s:min-label-width="%sin"/>%s' \
              '\n  </%s:list-level-style-%s>' % (nsText, self.type, nsText, i+1,
              nsText, self.textStyle, self.getLevelAttributes(i,nsText,nsStyle),
              nsStyle, nsText, sb, nsText, space,
              self.getTextProperties(i, nsText, nsStyle), nsText, self.type)
            res.append(level)
        res = u'<%s:list-style %s:name="%s">\n%s\n</%s:list-style>' % \
               (nsText, nsStyle, name, u'\n'.join(res), nsText)
        return res.encode('utf-8')

class BulletedProperties(ListProperties):
    '''In a styles mapping, the value @key "ul" must be an instance of this
       class.'''
    type = 'bullet'
    defaultFormats = (u'•', u'◦', u'▪')
    textStyle = 'podBulletStyle'
    def __init__(self, levels=4, formats=defaultFormats,
                 delta=0.25, space=0.25):
        ListProperties.__init__(self, levels, formats, delta, space)

    def getLevelAttributes(self, i, nsText, nsStyle):
        '''Dumps bullet-specific attributes for level p_i'''
        # Get the bullet to render at this level
        return u'%s:bullet-char="%s"' % (nsText, getElementAt(self.formats, i))

    def getTextProperties(self, i, nsText, nsStyle):
        '''Gets the text properties at level p_i.'''
        return u'\n    <%s:text-properties %s:font-name="PodStarSymbol"/>' % \
               (nsStyle, nsStyle)

class NumberedProperties(ListProperties):
    '''In a styles mapping, the value @key "ol" must be an instance of this
       class.'''
    type = 'number'
    defaultFormats = ('1',)
    defaultSuffixes = ('.',)
    textStyle = 'podNumberStyle'
    def __init__(self, levels=4, formats=defaultFormats,
                 suffixes=defaultSuffixes, delta=0.25, space=0.25):
        ListProperties.__init__(self, levels, formats, delta, space)
        # The list of suffixes
        self.suffixes = suffixes

    def getLevelAttributes(self, i, nsText, nsStyle):
        '''Dumps number-specific attributes for level p_i'''
        # Get the number type and suffix to render at this level
        return '%s:num-suffix="%s" %s:num-format="%s"' % \
               (nsStyle, getElementAt(self.suffixes, i),
                nsStyle, getElementAt(self.formats, i))

    def getTextProperties(self, i, nsText, nsStyle): return ''

# ------------------------------------------------------------------------------
class Style:
    '''Represents an ODF style. Either parsed from an ODF file or used for
       dumping a style into an ODF file.'''
    numberRex = re.compile('(\d+)(.*)')

    def __init__(self, name, family, defaults=None, outlineLevel=None):
        self.name = name
        self.family = family # May be 'paragraph', etc.
        self.displayName = name
        self.styleClass = None # May be 'text', 'list', etc.
        self.fontSize = None
        self.fontSizeUnit = None # May be pt, %, ...
        # Were the styles lies within styles and substyles hierarchy
        self.outlineLevel = outlineLevel
        # Namespace for the ODF "style-name" attribute corresponding to this
        # style
        self.styleNameNs = (family == 'table-cell') and 'table' or 'text'
        # Default ODF attributes for this style
        self.defaults = defaults
        # For some unknown reason, ODF parent-child links don't work
        self.inheritWorks = family != 'table-cell'

    def setFontSize(self, fontSize):
        rexRes = self.numberRex.search(fontSize)
        self.fontSize = int(rexRes.group(1))
        self.fontSizeUnit = rexRes.group(2)

    def __repr__(self):
        res = '<Style %s|family %s' % (self.name, self.family)
        if self.displayName != None: res += '|displayName "%s"'%self.displayName
        if self.styleClass != None: res += '|class %s' % self.styleClass
        if self.fontSize != None:
            res += '|fontSize %d%s' % (self.fontSize, self.fontSizeUnit)
        if self.outlineLevel != None: res += '|level %s' % self.outlineLevel
        return ('%s>' % res).encode('utf-8')

    def getOdfAttributes(self, attrs=None, withName=True, withDefaults=False,
                         exclude=None):
        '''Gets the ODF attributes corresponding to this style. p_attrs, when
           given, are attributes of an XHTML tag.'''
        # Style name
        res = ''
        if withName:
            res = ' %s:style-name="%s"' % (self.styleNameNs, self.name)
        # Outline level when relevant
        if self.outlineLevel != None:
            res += ' text:outline-level="%d"' % self.outlineLevel
        # Colspan and rowspan when relevant
        if attrs and attrs.has_key('colspan'):
            res += ' table:number-columns-spanned="%s"' % attrs['colspan']
        if attrs and attrs.has_key('rowspan'):
            res += ' table:number-rows-spanned="%s"' % attrs['rowspan']
        # Additional parameters as stored in self.defaults
        if withDefaults and self.defaults:
            for name, value in self.defaults.iteritems():
                if exclude and (name in exclude): continue
                res += ' %s="%s"' % (name, value)
        return res

    def getOdfParentAttributes(self, childAttrs=None):
        '''If style inheritance works, this method simply returns the attribute
           "style:parent-style-name" allowing to define some style as child from
           this one. If inheritance does not work (like for "table-cell"
           styles), this method returns, in extenso, the parent ODF properties,
           so they will be entirely copied into the child style.'''
        if self.inheritWorks:
            return ' style:parent-style-name="%s"' % self.name
        else:
            return self.getOdfAttributes(withName=False, withDefaults=True,
                                         exclude=childAttrs)

# Default ODF styles for XHTML elements. They correspond to styles from
# content.xmlt or styles.xmlt. Default cell and header attributes are repeated
# here because, for an unknown reason, they are not inherited from default
# styles defined in styles.xmlt when generating a child sub-style.
DEFAULT_CELL_PARAMS = {'fo:padding':'0.1cm','fo:border':'0.018cm solid #000000'}
DEFAULT_HEADER_PARAMS = DEFAULT_CELL_PARAMS.copy()
DEFAULT_HEADER_PARAMS['fo:background-color'] = '#e6e6e6'
DEFAULT_STYLES = {
  'b': Style('podBold', 'text'), 'strong': Style('podBold', 'text'),
  'i': Style('podItalic', 'text'), 'u': Style('podUnderline', 'text'),
  'strike': Style('podStrike', 'text'), 's': Style('podStrike', 'text'),
  'em': Style('podItalic', 'text'), 'sup': Style('podSup', 'text'),
  'sub': Style('podSub', 'text'), 'table': TableProperties(),
  'td': Style('podCell', 'table-cell', DEFAULT_CELL_PARAMS),
  'th': Style('podHeader', 'table-cell', DEFAULT_HEADER_PARAMS),
}
for i in range(1,7):
    DEFAULT_STYLES['h%d'%i] = Style('podH%d'%i, 'paragraph', outlineLevel=i)

# ------------------------------------------------------------------------------
class PageLayout:
    '''Represents a kind of page-level style.'''
    def __init__(self, name):
        self.name = name

    def getFloat(self, value):
        '''Extract the float value from the string p_value'''
        res = ''
        for c in value:
            if c.isdigit() or (c == '.'):
                res += c
        return float(res)

    def setProperties(self, e, attrs):
        '''Sets properties of this page layout based on parsed p_attrs from tag
           "page-layout-properties".'''
        # Compute page dimensions. May be missing for ods files.
        widthAttr = e.tags['page-width']
        if not attrs.has_key(widthAttr): return
        self.width = self.getFloat(attrs[widthAttr])
        heightAttr = e.tags['page-height']
        if not attrs.has_key(heightAttr): return
        self.height = self.getFloat(attrs[heightAttr])
        # Compute margins
        marginAttr = e.tags['margin']
        if not attrs.has_key(marginAttr):
            defaultMargin = '2cm'
        else:
            defaultMargin = attrs[marginAttr]
        for margin in ('top', 'right', 'bottom', 'left'):
            key = e.tags['margin-%s' % margin]
            value = attrs.has_key(key) and attrs[key] or defaultMargin
            marginAttr = 'margin%s' % margin.capitalize()
            setattr(self, marginAttr, self.getFloat(value))

    def getWidth(self, substractMargins=True):
        '''Return, as a float, the page width in cm'''
        res = self.width
        if substractMargins: res -= self.marginLeft + self.marginRight
        return res

    def __repr__(self): return '<Page layout %s>' % self.name

# ------------------------------------------------------------------------------
class Styles(UserDict):
    def getParagraphStyleAtLevel(self, level):
        '''Tries to find a style which has level p_level. Returns None if no
           such style exists.'''
        for style in self.itervalues():
            if (style.family == 'paragraph') and (style.outlineLevel == level):
                return style

    def getStyle(self, displayName):
        '''Gets the style that has this p_displayName. Returns None if not
           found.'''
        res = None
        for style in self.itervalues():
            if style.displayName == displayName:
                res = style
                break
        return res

    def getStyles(self, stylesType='all'):
        '''Returns a list of all the styles of the given p_stylesType'''
        res = []
        if stylesType == 'all':
            res = self.values()
        else:
            for style in self.itervalues():
                if (style.family == stylesType) and style.displayName:
                    res.append(style)
        return res

# ------------------------------------------------------------------------------
class StylesEnvironment(OdfEnvironment):
    def __init__(self):
        OdfEnvironment.__init__(self)
        # Namespace definitions are not already encountered
        self.gotNamespaces = False
        # Names of some tags, that we will compute after namespace propagation
        self.tags = None
        self.styles = Styles()
        self.currentStyle = None # The currently parsed style definition
        # The found page layouts, keyed by their name
        self.pageLayouts = {}
        self.currentPageLayout = None # The currently parsed page layout
        # The name of the page layout defined for the whole document
        self.masterLayoutName = None
        self.state = READING

    def onStartElement(self):
        ns = self.namespaces
        if not self.gotNamespaces:
            # We suppose that all the interesting (from the POD point of view)
            # XML namespace definitions are defined at the root XML element.
            # Here we propagate them in XML element definitions that we use
            # throughout POD.
            self.gotNamespaces = True
            self.propagateNamespaces()
        return ns

    def propagateNamespaces(self):
        '''Propagates the namespaces in all XML element definitions that are
           used throughout POD.'''
        ns = self.namespaces
        # Create a table of names of used tags and attributes (precomputed,
        # including namespace, for performance).
        style = ns[self.NS_STYLE]
        fo = ns[self.NS_FO]
        office = ns[self.NS_OFFICE]
        tags = {
          'style': '%s:style' % style,
          'name': '%s:name' % style,
          'family': '%s:family' % style,
          'class': '%s:class' % style,
          'display-name': '%s:display-name' % style,
          'default-outline-level': '%s:default-outline-level' % style,
          'text-properties': '%s:text-properties' % style,
          'font-size': '%s:font-size' % fo,
          'master-styles': '%s:master-styles' % office,
          'master-page': '%s:master-page' % style,
          'page-layout-name': '%s:page-layout-name' % style,
          'page-layout': '%s:page-layout' % style,
          'page-layout-properties': '%s:page-layout-properties' % style,
          'page-width': '%s:page-width' % fo,
          'page-height': '%s:page-height' % fo,
          'margin': '%s:margin' % fo,
          'margin-top': '%s:margin-top' % fo,
          'margin-right': '%s:margin-right' % fo,
          'margin-bottom': '%s:margin-bottom' % fo,
          'margin-left': '%s:margin-left' % fo,
        }
        self.tags = tags

# ------------------------------------------------------------------------------
class StylesParser(OdfParser):
    def __init__(self, env, caller):
        OdfParser.__init__(self, env, caller)

    def endDocument(self):
        e = OdfParser.endDocument(self)
        self.caller.styles = e.styles
        self.caller.pageLayout = e.pageLayouts[e.masterLayoutName]

    def startElement(self, elem, attrs):
        e = OdfParser.startElement(self, elem, attrs)
        ns = e.onStartElement()
        if elem == e.tags['style']:
            e.state = PARSING_STYLE
            # Create the style
            style = Style(name=attrs[e.tags['name']],
                          family=attrs[e.tags['family']])
            classAttr = e.tags['class']
            if attrs.has_key(classAttr): style.styleClass = attrs[classAttr]
            dnAttr = e.tags['display-name']
            if attrs.has_key(dnAttr): style.displayName = attrs[dnAttr]
            dolAttr = e.tags['default-outline-level']
            if attrs.has_key(dolAttr) and attrs[dolAttr].strip():
                style.outlineLevel = int(attrs[dolAttr])
            # Record this style in the environment
            e.styles[style.name] = style
            e.currentStyle = style

        elif elem == e.tags['page-layout']:
            e.state = PARSING_PAGE_LAYOUT
            pageLayout = PageLayout(attrs[e.tags['name']])
            # Record this page layout in the environment
            e.pageLayouts[pageLayout.name] = pageLayout
            e.currentPageLayout = pageLayout

        elif elem == e.tags['master-styles']:
            e.state = PARSING_MASTER_STYLES

        elif e.state == PARSING_STYLE:
            # Find properties within this style definition
            if elem == e.tags['text-properties']:
                fontSizeAttr = e.tags['font-size']
                if attrs.has_key(fontSizeAttr):
                    e.currentStyle.setFontSize(attrs[fontSizeAttr])

        elif e.state == PARSING_PAGE_LAYOUT:
            # Find properties within this page layout definition
            if elem == e.tags['page-layout-properties']:
                e.currentPageLayout.setProperties(e, attrs)

        elif e.state == PARSING_MASTER_STYLES:
            # I am parsing section "master-styles"
            if elem == e.tags['master-page']:
                plnAttr = e.tags['page-layout-name']
                if attrs.has_key(plnAttr):
                    e.masterLayoutName = attrs[plnAttr]


    def endElement(self, elem):
        e = OdfParser.endElement(self, elem)
        if elem == e.tags['style']:
            e.state = READING
            e.currentStyle = None
        elif elem == e.tags['page-layout']:
            e.state = READING
            e.currentPageLayout = None
        elif elem == e.tags['master-styles']:
            e.state = READING

# ------------------------------------------------------------------------------
class Css2odf:
    '''Allows to get a OpenDocument attribute from a CSS attribute'''
    # Map CSS attribute names to ODF attribute names. CSS attributes names
    # have lost their inner dashes (margin-left => marginleft) because they are
    # used as Python attributes on CssStyles instances.
    namesMap = {
      'marginleft': 'fo:margin-left', 'marginright': 'fo:margin-right',
      'margintop': 'fo:margin-top', 'marginbottom': 'fo:margin-bottom',
      'textalign': 'fo:text-align', 'textindent': 'fo:text-indent',
      'backgroundcolor': 'fo:background-color', 'color': 'fo:color',
      'fontsize': 'fo:font-size', 'fontvariant': 'fo:font-variant',
      'fontweight': 'fo:font-weight', 'fontstyle': 'fo:font-style',
      'verticalalign': 'style:vertical-align', 'border': 'fo:border',
      'borderspacing': 'fo:padding',
      # CSS text-decoration corresponds to a different ODF attribute, depending
      # on its value.
      'textdecoration': {
        'underline': ('style:text-underline-style', 'solid'),
        'line-through': ('style:text-line-through-style', 'solid'),
        'overline': ('style:text-overline-style', 'solid')}}
    # Map XHTML CSS values to values of their corresponding ODF attributes when
    # they are different.
    valuesMap = {'textalign': {'left': 'start', 'center': 'center',
                               'right': 'end', 'justify': 'justify'},
                 'border': {'0': 'none'}}

    def getOdf(self, name, value):
        '''Get the ODF attribute, as a tuple (name, value), corresponding to
           CSS attribute p_name having some p_value.'''
        # Is there an ODF attribute corresponding to this CSS attribute ?
        odfName = self.namesMap.get(name)
        if not odfName: return
        # Is the ODF attribute different according to CSS value ?
        elif isinstance(odfName, dict):
            return odfName[value.value]
        # Standardize the attribute for use within an ODF document
        unit = value.unit or ''
        odfValue = value.value
        if unit == 'px': # Convert pixels to cm
            odfValue = float(odfValue) / px2cmRatio
            odfValue = formatNumber(odfValue, sep='.', precision=3)
            unit = 'cm'
        # Convert the value to the ODF equivalent when needed
        if not unit and (name in self.valuesMap):
            odfValue = self.valuesMap[name][odfValue]
        return odfName, '%s%s' % (odfValue, unit)

# ------------------------------------------------------------------------------
class StylesGenerator:
    '''Analyse, for a given XHTML tag, its attributes (including CSS attributes
       within the "style" attribute) and possibly generate a custom style.'''
    prefix = 'CS' # Stands for *C*ustom *S*tyle
    # Map HTML tags to ODF style families
    styleFamilies = {'p': 'paragraph', 'div': 'paragraph', 'td': 'table-cell',
                     'th': 'table-cell', 'span': 'text'}
    # For paragraph styles, there are 2 kinds of properties: paragraph and text
    # properties. Any property not being listed as a text property below will be
    # considered as a paragraph property.
    textProperties = ('fo:color', 'fo:font-size', 'fo:font-variant',
      'fo:font-weight', 'fo:font-style', 'style:text-underline-style',
      'style:text-line-through-style', 'style:text-overline-style')
    # Properties applying to table cells and that are not transferred to inner
    # paragraphs.    
    cellProperties = ('fo:padding', 'fo:border', 'fo:background-color',
                      'style:vertical-align')
    # Default parent styles to apply for generated styles. Those styles are not
    # listed among DEFAULT_STYLES because, when there is no custom style to
    # generate, they must not be specified, it is implicit.
    standardStyle = Style('Standard', 'paragraph')
    defaultParents = {'p': standardStyle, 'div': standardStyle, 'span': None}

    def __init__(self, stylesManager):
        self.last = 0 # The number attributed to the last generated style
        # The names of the styles that were already generated, keyed by some
        # hash value
        self.generated = {}
        self.stylesManager = stylesManager
        self.css2odf = Css2odf() # Allows to convert CSS to ODF attributes

    def addStyle(self, style, target):
        '''Adds the style definition to the renderer's dynamic styles.
           Target is "styles" (styles.xml) or "content" (content.xml).'''
        dynamicStyles = self.stylesManager.renderer.dynamicStyles[target]
        dynamicStyles.append(style.encode('utf-8'))

    def getStyleHash(self, xhtmlElem, odfAttrs):
        '''Returns a string uniquely representing the given set of ODF
           attributes p_odfAttrs that will be used to create/retrieve a style to
           be applied to the ODF element corresponding to p_xhtmlElem.'''
        odfAttrs.sort()
        attrs = self.flattenOdfAttributes(odfAttrs, forHash=True)
        return '%s%s' % (xhtmlElem.elem, ''.join(attrs))

    def getStyleName(self, xhtmlElem, odfAttrs):
        '''Return the ODF style name for the style that will be applied to ODF
           element corresponding to the given XHTML element (p_xhtmlElem). We
           have already computed attributes for the ODF style in p_odfAttrs. If
           a style has already been generated by this styles generator, for this
           tag and with this combination of attributes, we simply return its
           name. Else, we note that we must generate a new style; we compute a
           new (incremental) name for it and we return this name.

           More precisely, this method returns a tuple (createNew, styleName):
            - "createNew" is a boolean indicating if a new style must be
                          generated;
            - "styleName" is the style name.'''
        # If the style hash corresponds to an existing style, simply return
        # its name
        hash = self.getStyleHash(xhtmlElem, odfAttrs)
        if hash in self.generated:
            return False, self.generated[hash]
        # We must generate a new style
        self.last += 1
        res = '%s%d' % (self.prefix, self.last)
        self.generated[hash] = res
        return True, res

    def flattenOdfAttributes(self, odfAttrs, forHash=False):
        '''Produce a string from the list of (name, value) pairs in
           p_odfAttrs.'''
        fmt = forHash and '%s%s' or '%s="%s"'
        return [fmt % (name, value) for name, value in odfAttrs]

    # There is one method for generating every HTML tag
    def get_p(self, xhtmlElem, odfAttrs, baseStyle):
        '''Generates a paragraph style'''
        createNew, styleName = self.getStyleName(xhtmlElem, odfAttrs)
        if not createNew: return styleName
        # Generate a new style. Is there a parent style ?
        baseStyle = baseStyle or self.defaultParents[xhtmlElem.elem]
        names = [name for name, value in odfAttrs]
        parent = baseStyle and baseStyle.getOdfParentAttributes(names) or ''
        # Among p_odfAttrs, distinguish "paragraph" and "text" properties
        paraAttrs = []
        textAttrs = []
        for name, value in odfAttrs:
            if name in self.textProperties:
                textAttrs.append((name, value))
            else:
                paraAttrs.append((name, value))
        paraProps = textProps = ''
        if paraAttrs:
            paraProps = '<style:paragraph-properties %s/>' % \
                        ' '.join(self.flattenOdfAttributes(paraAttrs))
        if textAttrs:
            textProps = '<style:text-properties %s/>' % \
                        ' '.join(self.flattenOdfAttributes(textAttrs))
        family = self.styleFamilies[xhtmlElem.elem]
        style = '<style:style style:name="%s" style:family="%s"%s>%s%s' \
                '</style:style>' % (styleName,family,parent,textProps,paraProps)
        # I could have added this style in content.xml. But in some cases it
        # does not work properly. For example, a percentage value for attribute
        # "fo-font-size" will be ignored if the style is dumped in content.xml.
        self.addStyle(style, 'styles')
        return styleName
    get_div = get_span = get_p

    def get_td(self, xhtmlElem, odfAttrs, baseStyle):
        '''Generates a table cell style'''
        # If there is a "text-related" property among p_odfAttrs, we must
        # generate a style for the inner-paragraph within this cell. Indeed, in
        # XHTML, this kind of information can be defined at the "td" tag level,
        # while, in ODF, it must be defined at the inner-paragraph level. A cell
        # style will only be generated if there is a "cell-related" property
        # among p_odfAttrs.
        paraAttrs = []
        cellAttrs = []
        for name, value in odfAttrs:
            if name == 'fo:text-align': paraAttrs.append((name, value))
            elif name in self.textProperties: paraAttrs.append((name, value))
            elif name in self.cellProperties: cellAttrs.append((name, value))
        # Generate a paragraph style to be applied on this td's inner paragraph
        if paraAttrs:
            xhtmlElem.innerStyle = self.get_p(xhtmlElem.protos['p'], paraAttrs,
                                           Style('podCellContent', 'paragraph'))
        # Generate a cell style
        if cellAttrs:
            # Generate (or retrieve) a table-cell style, based on the standard
            # Appy cell style.
            createNew, styleName = self.getStyleName(xhtmlElem, cellAttrs)
            if not createNew: return styleName
            # Generate a new style. For table cells there is always a baseStyle.
            names = [name for name, value in cellAttrs]
            style = '<style:style style:name="%s" style:family="%s">' \
              '<style:table-cell-properties%s %s/></style:style>' % \
              (styleName, self.styleFamilies[xhtmlElem.elem],
               baseStyle.getOdfParentAttributes(names),
               ' '.join(self.flattenOdfAttributes(cellAttrs)))
            self.addStyle(style, 'content')
            return styleName
    get_th = get_td

    def get(self, xhtmlElem, attrs, baseStyle):
        '''Generates a custom style when relevant. p_baseStyle is a Style
           instance that could have been found from a style mapping. In this
           case, the generated style will get it as parent style.'''
        # If there is no p_attrs, no custom style can be defined
        if not attrs: return baseStyle
        # If the style is a [Table|List]Properties instance, return it. The
        # caller will generate the style himself.
        if (isinstance(baseStyle, TableProperties) or \
            isinstance(baseStyle, ListProperties)): return baseStyle
        # Analyse p_attrs
        elem = xhtmlElem.elem
        cssStyles = CssStyles(elem, attrs)
        if not cssStyles: return baseStyle
        # Collect ODF attributes corresponding to CSS attributes
        odfAttrs = []
        for name, value in cssStyles.get().iteritems():
            odf = self.css2odf.getOdf(name, value)
            if odf: odfAttrs.append(odf)
        if not odfAttrs: return baseStyle
        # I have attributes to apply. Call the corresponding "get_[tag]" method
        # for generating a custom style.
        method = 'get_%s' % elem
        # We may not be able to produce styles for this tag (yet)
        if not hasattr(self, method): return baseStyle
        styleName = getattr(self, method)(xhtmlElem, odfAttrs, baseStyle)
        # "styleName" may be empty. For example, it may not be necessary to
        # generate a custom style for a "td", although we must generate, from
        # its attrs, a custom style for its inner-paragraph.
        if not styleName: return baseStyle
        return Style(styleName, self.styleFamilies[elem])

# ------------------------------------------------------------------------------
class StylesManager:
    '''Reads the paragraph styles from styles.xml within an ODT file, and
       updates styles.xml with some predefined POD styles.'''
    podSpecificStyles = {
      'ParaKWN': Style('ParaKWN', 'paragraph'),
      # This style is common to bullet and number items. Behind the scenes,
      # there are 2 concrete ODT styles: podBulletItemKeepWithNext and
      # podNumberItemKeepWithNext. pod chooses the right one.
      'podItemKeepWithNext': Style('podItemKeepWithNext', 'paragraph'),
    }
    # Valid value types for some keys within style mappings
    mappingValueTypes = {'h*': int, 'table': TableProperties,
                         'ol': NumberedProperties, 'ul': BulletedProperties}
    def __init__(self, renderer):
        self.renderer = renderer
        self.stylesString = renderer.stylesXml
        # The collected styles, as a list of Style instances
        self.styles = None
        # The main page layout, as a PageLayout instance
        self.pageLayout = None
        # Global styles mapping
        self.stylesMapping = None
        self.stylesParser = StylesParser(StylesEnvironment(), self)
        self.stylesParser.parse(self.stylesString)
        # Now self.styles contains the styles.
        # Text styles from self.styles
        self.textStyles = self.styles.getStyles('text')
        # Paragraph styles from self.styles
        self.paragraphStyles = self.styles.getStyles('paragraph')
        # The custom styles generator
        self.stylesGenerator = StylesGenerator(self)

    def checkStylesAdequation(self, htmlStyle, odtStyle):
        '''Checks that p_odtStyle may be used for style p_htmlStyle'''
        if (htmlStyle in XHTML_PARAGRAPH_TAGS_NO_LISTS) and \
            (odtStyle in self.textStyles):
            raise PodError(
                HTML_PARA_ODT_TEXT % (htmlStyle, odtStyle.displayName))
        if (htmlStyle in XHTML_INNER_TAGS) and \
            (odtStyle in self.paragraphStyles):
            raise PodError(HTML_TEXT_ODT_PARA % (
                htmlStyle, odtStyle.displayName))

    def checkStylesMapping(self, stylesMapping):
        '''Checks that the given p_stylesMapping is correct, and returns the
           internal representation of it. p_stylesMapping is a dict where:
           * every key can be:
             (1) the name of a XHTML 'paragraph-like' tag (p, h1, h2...);
             (2) the name of a XHTML 'text-like' tag (span, b, i, em...);
             (3) the name of a CSS class;
             (4) string 'h*';
             (5) 'table';
             (6) 'ol' or 'ul'.
           * every value must be:
             (a) if the key is (1), (2) or (3), value must be the display name
                 of an ODT style;
             (b) if the key is (4), value must be an integer indicating how to
                 map the outline level of outlined styles (ie, for mapping XHTML
                 tag "h1" to the OD style with outline-level=2, value must be
                 integer "1". In that case, h2 will be mapped to the ODT style
                 with outline-level=3, etc.). Note that this value can also be
                 negative;
             (c) if key is "table", the value must be a TableProperties instance
                 (this class is defined hereabove);
             (d) if key is "ol", the value must be an instance of the
                 hereabove-defined NumberedProperties class; if key is "ul", the
                 value must be an instance of the hereabove-defined
                 BulletedProperties class.
           * Some precision now about about keys. If key is (1) or (2),
             parameters can be given between square brackets. Every such
             parameter represents a CSS attribute and its value. For example, a
             key can be:
                             p[text-align=center,color=blue]

             This feature allows to map XHTML tags having different CSS
             attributes to different ODT styles.

           The method returns a dict which is the internal representation of
           the styles mapping:
           * every key can be:
             (I) the name of a XHTML tag, corresponding to (1), (2), (5) or (6)
                 whose potential parameters have been removed;
             (II) the name of a CSS class (=(3))
             (III) string 'h*' (=(4))
           * every value can be:
             (i) a Style instance that was found from the specified ODT style
                 display name in p_stylesMapping, if key is (I) and if only one
                 non-parameterized XHTML tag was defined in p_stylesMapping;
             (ii) a list of the form [ (params, Style), (params, Style),...]
                  if key is (I) and if one or more parameterized (or not) XHTML
                  tags representing the same tag were found in p_stylesMapping.
                  params, which can be None, is a dict whose pairs are of the
                  form (cssAttribute, cssValue).
             (iii) an integer value (=(b));
             (iv) a [x]Properties instance if cases (5) or (6).
        '''
        res = {}
        if not isinstance(stylesMapping, dict) and \
           not isinstance(stylesMapping, UserDict):
            raise PodError(MAPPING_NOT_DICT)
        for xhtmlStyleName, odtStyleName in stylesMapping.iteritems():
            if not isinstance(xhtmlStyleName, basestring):
                raise PodError(MAPPING_KEY_NOT_STRING)
            # Separate CSS attributes if any
            cssAttrs = None
            if '[' in xhtmlStyleName:
                xhtmlStyleName, attrs = xhtmlStyleName.split('[')
                xhtmlStyleName = xhtmlStyleName.strip()
                attrs = attrs.strip()[:-1].split(',')
                cssAttrs = {}
                for attr in attrs:
                    name, value = attr.split('=')
                    cssAttrs[name.strip()] = value.strip()
            # Continue checks
            if xhtmlStyleName in StylesManager.mappingValueTypes:
                vType = StylesManager.mappingValueTypes[xhtmlStyleName]
                if not isinstance(odtStyleName, vType):
                    raise PodError(MAPPING_WRONG_VALUE_TYPE % \
                                   (xhtmlStyleName, vType.__name__))
            else:
                if not isinstance(odtStyleName, basestring):
                    raise PodError(MAPPING_ELEM_NOT_STRING % xhtmlStyleName)
                if not xhtmlStyleName or not odtStyleName:
                    raise PodError(MAPPING_ELEM_EMPTY)
            if xhtmlStyleName in XHTML_UNSTYLABLE_TAGS:
                raise PodError(UNSTYLABLE_TAG % (xhtmlStyleName,
                                                 XHTML_UNSTYLABLE_TAGS))
            if xhtmlStyleName not in StylesManager.mappingValueTypes:
                odtStyle = self.styles.getStyle(odtStyleName)
                if not odtStyle:
                    if self.podSpecificStyles.has_key(odtStyleName):
                        odtStyle = self.podSpecificStyles[odtStyleName]
                    else:
                        raise PodError(STYLE_NOT_FOUND % odtStyleName)
                self.checkStylesAdequation(xhtmlStyleName, odtStyle)
                # Store this style mapping in the result
                alreadyInRes = xhtmlStyleName in res
                if cssAttrs or alreadyInRes:
                    # I must create a complex structure (ii) for this mapping
                    if not alreadyInRes:
                        res[xhtmlStyleName] = [(cssAttrs, odtStyle)]
                    else:
                        value = res[xhtmlStyleName]
                        if not isinstance(value, list):
                            res[xhtmlStyleName] = [(cssAttrs, odtStyle), \
                                                   (None, value)]
                        else:
                            res.insert(0, (cssAttrs, odtStyle))
                else:
                    # I must create a simple structure (i) for this mapping
                    res[xhtmlStyleName] = odtStyle
            else:
                # In this case (iii, iv), it is the outline level or a
                # [x]Properties instance.
                res[xhtmlStyleName] = odtStyleName
        return res

    def setStylesMapping(self, stylesMapping):
        '''Initialises the global p_stylesMapping and ensures that some default
           entries are in it'''
        # The predefined styles below are currently ignored, because the
        # xhtml2odt parser does not take into account span tags.
        if 'span[font-weight=bold]' not in stylesMapping:
            stylesMapping['span[font-weight=bold]'] = 'podBold'
        if 'span[font-style=italic]' not in stylesMapping:
            stylesMapping['span[font-style=italic]'] = 'podItalic'
        self.stylesMapping = stylesMapping

    def styleMatch(self, attrs, matchingAttrs):
        '''p_attrs is a dict of attributes found on some HTML element.
           p_matchingAttrs is a dict of attributes corresponding to some style.
           This method returns True if p_attrs contains the winning (name,value)
           pairs that match those in p_matchingAttrs. Note that ALL attrs in
           p_matchingAttrs must be present in p_attrs.'''
        for name, value in matchingAttrs.iteritems():
            if name not in attrs: return
            if value != attrs[name]: return
        return True

    def getStyleFromMapping(self, elem, attrs, styles):
        '''p_styles is a value from a styles mapping as transformed by
           m_checkStylesMapping above. If it represents a list of styles
           (see case (ii) in m_checkStylesMapping), this method must return the
           relevant Style instance form this list, depending on CSS attributes
           found in p_attrs.'''
        if not isinstance(styles, list): return styles
        hasStyleInfo = attrs and ('style' in attrs)
        if not hasStyleInfo:
            # If I have, at the last position in p_styles, the style related to
            # no attribute at all, I return it.
            lastAttrs, lastStyle = styles[-1]
            if lastAttrs == None: return lastStyle
            else: return
        # If I am here, I have style info. Check if it corresponds to some style
        # in p_styles.
        styleInfo = parseStyleAttribute(attrs['style'], asDict=True)
        for matchingAttrs, style in styles:
            if self.styleMatch(styleInfo, matchingAttrs):
                return style

    def findStyle(self, xhtmlElem, attrs, classValue, localStylesMapping):
        '''Finds the ODT style that must be applied to XHTML p_elem (as a
           xhtml2odt:HtmlElement instance) and its p_attrs. In some cases,
           p_attrs is None; the value of the "class" attribute is given
           instead (in p_classValue).

           The global styles mapping is in self.stylesMapping; the local styles
           mapping is in p_localStylesMapping.

           Here are the places where we will search, ordered by
           priority (highest first):
           (1) local styles mapping (CSS style in "class" attr)
           (2)         "            (HTML elem)
           (3) global styles mapping (CSS style in "class" attr)
           (4)          "            (HTML elem)
           (5) ODT style that has the same name as CSS style in "class" attr
           (6) Predefined pod-specific ODT style that has the same name as
               CSS style in "class" attr
           (7) ODT style that has the same outline level as HTML elem
           (8) a default Appy ODT style
        
        After this step, we have (or not) a base ODT style. In a final step we
        will analyse XHTML attributes (including CSS attributes within the
        "style" attribute) to get more elements and possibly generate, via the
        styles generator define hereabove, a custom style based on the base
        ODT style.'''
        res = None
        cssStyleName = None
        elem = xhtmlElem.elem
        if attrs and attrs.has_key('class'):
            cssStyleName = attrs['class']
        if classValue:
            cssStyleName = classValue
        # (1)
        if localStylesMapping.has_key(cssStyleName):
            res = localStylesMapping[cssStyleName]
        # (2)
        if not res and localStylesMapping.has_key(elem):
            styles = localStylesMapping[elem]
            res = self.getStyleFromMapping(elem, attrs, styles)
        # (3)
        if not res and self.stylesMapping.has_key(cssStyleName):
            res = self.stylesMapping[cssStyleName]
        # (4)
        if not res and self.stylesMapping.has_key(elem):
            styles = self.stylesMapping[elem]
            res = self.getStyleFromMapping(elem, attrs, styles)
        # (5)
        if not res and self.styles.has_key(cssStyleName):
            res = self.styles[cssStyleName]
        # (6)
        if not res and self.podSpecificStyles.has_key(cssStyleName):
            res = self.podSpecificStyles[cssStyleName]
        # (7)
        if not res and (elem in XHTML_HEADINGS):
            # Try to find a style with the correct outline level. Is there a
            # delta that must be taken into account ?
            outlineDelta = 0
            if localStylesMapping.has_key('h*'):
                outlineDelta += localStylesMapping['h*']
            elif self.stylesMapping.has_key('h*'):
                outlineDelta += self.stylesMapping['h*']
            outlineLevel = int(elem[1]) + outlineDelta
            # Normalize the outline level
            if outlineLevel < 1: outlineLevel = 1
            res = self.styles.getParagraphStyleAtLevel(outlineLevel)
        # (8)
        if not res and (elem in DEFAULT_STYLES): res = DEFAULT_STYLES[elem]
        # Check styles adequation
        if res: self.checkStylesAdequation(elem, res)
        # Get or generate a custom style if there are specific CSS attributes
        return self.stylesGenerator.get(xhtmlElem, attrs, res)
# ------------------------------------------------------------------------------
