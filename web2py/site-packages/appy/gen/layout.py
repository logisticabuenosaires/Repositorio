'''This module contains classes used for layouting graphical elements
   (fields, widgets, groups, ...).'''

# A layout defines how a given field is rendered in a given context. Several
# contexts exist:
#  "view"   represents a given page for a given Appy class, in read-only mode.
#  "edit"   represents a given page for a given Appy class, in edit mode.
#  "cell"   represents a cell in a table, like when we need to render a field
#           value in a query result or in a reference table.
#  "search" represents an advanced search screen.

# Layout elements for a class or page ------------------------------------------
#  s - The page summary, containing summarized information about the page or
#      class, workflow information and object history.
#  w - The widgets of the current page/class
#  n - The navigation panel (inter-objects navigation)
#  b - The range of buttons (intra-object navigation, save, edit, delete...)

# Layout elements for a field --------------------------------------------------
#  l -  "label"        The field label
#  d -  "description"  The field description (a description is always visible)
#  h -  "help"         Help for the field (typically rendered as an icon,
#                       clicking on it shows a popup with online help
#  v -  "validation"   The icon that is shown when a validation error occurs
#                       (typically only used on "edit" layouts)
#  r -  "required"     The icon that specified that the field is required (if
#                       relevant; typically only used on "edit" layouts)
#  f -  "field"        The field value, or input for entering a value.
#  c -  "changes"      The button for displaying changes to a field

# For every field of a Appy class, you can define, for every layout context,
# what field-related information will appear, and how it will be rendered.
# Variables defaultPageLayouts and defaultFieldLayouts defined below give the
# default layouts for pages and fields respectively.
# 
# How to express a layout? You simply define a string that is made of the
# letters corresponding to the field elements you want to render. The order of
# elements correspond to the order into which they will be rendered.

# ------------------------------------------------------------------------------
from appy.px import Px

# ------------------------------------------------------------------------------
rowDelimiters =  {'-':'middle', '=':'top', '_':'bottom'}
rowDelms = ''.join(rowDelimiters.keys())
cellDelimiters = {'|': 'center', ';': 'left', '!': 'right'}
cellDelms = ''.join(cellDelimiters.keys())

pxDict = {
  # Page-related elements
  's': 'pxHeader', 'w': 'pxFields', 'n': 'pxNavigationStrip', 'b': 'pxButtons',
  # Field-related elements
  'l': 'pxLabel', 'd': 'pxDescription', 'h': 'pxHelp', 'v': 'pxValidation',
  'r': 'pxRequired', 'c': 'pxChanges'}

# ------------------------------------------------------------------------------
class Cell:
    '''Represents a cell in a row in a table.'''
    def __init__(self, content, align, isHeader=False):
        self.align = align
        self.width = None
        self.content = None
        self.colspan = 1
        if isHeader:
            self.width = content
        else:
            self.content = [] # The list of widgets to render in the cell
            self.decodeContent(content)

    def __repr__(self):
        return '<Cell %s>' % self.content

    def decodeContent(self, content):
        digits = '' # We collect the digits that will give the colspan
        for char in content:
            if char.isdigit():
                digits += char
            else:
                # It is a letter corresponding to a macro
                if char in pxDict:
                    self.content.append(pxDict[char])
                elif char == 'f':
                    # The exact macro to call will be known at render-time
                    self.content.append('?')
        # Manage the colspan
        if digits:
            self.colspan = int(digits)

# ------------------------------------------------------------------------------
class Row:
    '''Represents a row in a table'''
    def __init__(self, content, valign, isHeader=False):
        self.valign = valign
        self.cells = []
        self.decodeCells(content, isHeader)
        # Compute the row length
        length = 0
        for cell in self.cells:
            length += cell.colspan
        self.length = length

    def __repr__(self):
        return '<Row %s (%d)>' % (str(self.cells), self.length)

    def decodeCells(self, content, isHeader):
        '''Decodes the given chunk of layout string p_content containing
           column-related information (if p_isHeader is True) or cell content
           (if p_isHeader is False) and produces a list of Cell instances.'''
        cellContent = ''
        for char in content:
            if char in cellDelimiters:
                align = cellDelimiters[char]
                self.cells.append(Cell(cellContent, align, isHeader))
                cellContent = ''
            else:
                cellContent += char
        # Manage the last cell if any
        if cellContent:
            self.cells.append(Cell(cellContent, 'left', isHeader))

# ------------------------------------------------------------------------------
class Table:
    '''Represents a table where to dispose graphical elements'''
    simpleParams = ('style', 'css_class', 'cellpadding', 'cellspacing', 'width',
                    'align')
    derivedRepls = {'view': 'hrvd', 'search': 'hrvd', 'cell': 'ldc'}

    # Render this Table instance, known in the context as "layout". If the
    # layouted object is a page, the "layout target" (where to look for sub-PXs)
    # will be the object whose page is shown; if the layouted object is a field,
    # the layout target will be this field.

    # Warning: when the layout type is "cell", the cell width and alignment must
    # not be defined by the cell layout, but by the outer column layout.
    pxRender = Px('''
     <table var="layoutCss=layout.css_class;
                 inTd=(layoutType == 'cell') and column|False"
       cellpadding=":layout.cellpadding"
       cellspacing=":layout.cellspacing"
       width=":not inTd and layout.width or ''"
       align=":not inTd and ztool.flipLanguageDirection(layout.align,dir) or ''"
       class=":tagCss and ('%s %s' % (tagCss, layoutCss)).strip() or layoutCss"
       style=":layout.style" id=":tagId" name=":tagName">

      <!-- The table header row -->
      <tr if="layout.headerRow" valign=":layout.headerRow.valign">
       <th for="cell in layout.headerRow.cells" width=":cell.width"
           align=":ztool.flipLanguageDirection(cell.align, dir)">
       </th>
      </tr>
      <!-- The table content -->
      <tr for="row in layout.rows" valign=":row.valign">
       <td for="cell in row.cells" colspan=":cell.colspan"
           align=":ztool.flipLanguageDirection(cell.align, dir)"
           class=":not loop.cell.last and 'cellGap' or ''">
        <x for="pxName in cell.content">
         <x var="px=(pxName == '?') and 'px%s' % layoutType.capitalize() \
                                    or pxName">:getattr(layoutTarget, px)</x>
         <img if="not loop.pxName.last" src=":url('space.gif')"/>
        </x>
       </td>
      </tr>
     </table>''')

    def __init__(self, layoutString=None, style=None, css_class='',
                 cellpadding=0, cellspacing=0, width='100%', align='left',
                 other=None, derivedType=None):
        if other:
            # We need to create a Table instance from another Table instance,
            # given in p_other. In this case, we ignore previous params.
            if derivedType != None:
                # We will not simply mimic p_other. If p_derivedType is:
                # - "view", p_other is an "edit" layout, and we must create the
                #           corresponding "view" layout;
                # - "cell" or "search", p_derivedFrom is a "view" layout.
                self.layoutString = Table.deriveLayout(other.layoutString,
                                                       derivedType)
            else:
                self.layoutString = other.layoutString
            source = 'other.'
        else:
            source = ''
            self.layoutString = layoutString
        # Initialise simple params, either from the true params, either from
        # the p_other Table instance.
        for param in Table.simpleParams:
            exec 'self.%s = %s%s' % (param, source, param)
        # The following attribute will store a special Row instance used for
        # defining column properties.
        self.headerRow = None
        # The content rows will be stored hereafter.
        self.rows = []
        self.decodeRows(self.layoutString)

    @staticmethod
    def deriveLayout(layout, derivedType):
        '''Returns a layout derived from p_layout'''
        res = layout
        for letter in Table.derivedRepls[derivedType]:
            res = res.replace(letter, '')
        # Strip the derived layout
        res = res.lstrip(rowDelms); res = res.lstrip(cellDelms)
        if derivedType == 'cell':
            res = res.rstrip(rowDelms); res = res.rstrip(cellDelms)
        return res

    def addCssClasses(self, css_class):
        '''Adds a single or a group of p_css_class.'''
        if not self.css_class: self.css_class = css_class
        else:
            self.css_class += ' ' + css_class
            # Ensures that every class appears once
            self.css_class = ' '.join(set(self.css_class.split()))

    def isHeaderRow(self, rowContent):
        '''Determines if p_rowContent specified the table header row or a
           content row.'''
        # Find the first char that is a number or a letter
        for char in rowContent:
            if char not in cellDelimiters:
                if char.isdigit(): return True
                else:              return False
        return True

    def decodeRows(self, layoutString):
        '''Decodes the given p_layoutString and produces a list of Row
           instances.'''
        # Split the p_layoutString with the row delimiters
        rowContent = ''
        for char in layoutString:
            if char in rowDelimiters:
                valign = rowDelimiters[char]
                if self.isHeaderRow(rowContent):
                    if not self.headerRow:
                        self.headerRow = Row(rowContent, valign, isHeader=True)
                else:
                    self.rows.append(Row(rowContent, valign))
                rowContent = ''
            else:
                rowContent += char
        # Manage the last row if any
        if rowContent:
            self.rows.append(Row(rowContent, 'middle'))

    def removeElement(self, elem):
        '''Removes given p_elem from myself'''
        macroToRemove = pxDict[elem]
        for row in self.rows:
            for cell in row.cells:
                if macroToRemove in cell.content:
                    cell.content.remove(macroToRemove)
        if elem in self.layoutString:
            self.layoutString = self.layoutString.replace(elem, '')

    def __repr__(self): return '<Table %s>' % self.layoutString

# Some base layouts to use, for fields and pages -------------------------------
# The default layouts for pages
defaultPageLayouts  = {
    'view': Table('w-b'), 'edit': Table('w-b', width=None)}
# A layout for pages, containing the page summary
summaryPageLayouts = {'view': Table('s-w-b'), 'edit': Table('w-b', width=None)}
widePageLayouts = {'view': Table('w-b'), 'edit': Table('w-b')}
centeredPageLayouts = {
    'view': Table('w|-b|', align='center'),
    'edit': Table('w|-b|', width=None, align='center')
}

# Default field layouts
fieldLayouts = {'normal': {True: 'lrv-f', False: 'lv-f'},
                'grid': {True: 'frvl', False: 'fvl'}}

def defaultFieldLayouts(field):
    '''Returns the default layouts for fields. Depends on:
       - the fact that a field is required or not;
       - the type of group into which the field is.
       If Type-subclass-specific default layouts are defined in
       SubType.getDefaultLayouts, they will override default ones as computed
       here. For every field, the user can also use other frequently used
       layouts that are defined as Type-subclass static attributes
       (ie Boolean.dLayouts).'''
    key = field.inGrid() and 'grid' or 'normal'
    return {'edit': fieldLayouts[key][field.required]}

# ------------------------------------------------------------------------------
class ColumnLayout:
    '''A "column layout" dictates the way a table column must be rendered. Such
       a layout is of the form: <name>[*width][,|!|`|`]
       * "name"   is the name of the field whose content must be shown in
                  column's cells;
       * "width"  is the width of the column. Any valid value for the "width"
                  attribute of the "td" HTML tag is accepted;
       * , | or ! indicates column alignment: respectively, left, centered or
                  right.
    '''
    def __init__(self, layoutString):
        self.layoutString = layoutString
    def get(self):
        '''Returns a list containing the separate elements that are within
           self.layoutString.'''
        consumed = self.layoutString
        # Determine column alignment
        align = 'left'
        lastChar = consumed[-1]
        if lastChar in cellDelimiters:
            align = cellDelimiters[lastChar]
            consumed = consumed[:-1]
        # Determine name and width
        if '*' in consumed:
            name, width = consumed.rsplit('*', 1)
        else:
            name = consumed
            width = ''
        return name, width, align
# ------------------------------------------------------------------------------
