# -*- coding: iso-8859-15 -*-
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

'''ODT table parser.

  This parser reads ODT documents that conform to the following.
   - Each table must have a first row with only one cell: the table name.
   - The other rows must all have the same number of columns. This number must
     be strictly greater than 1.'''

# ------------------------------------------------------------------------------
import os, os.path, re, time, UserList, UserDict
from utils import getOsTempFolder, FolderDeleter
from zip import unzip
from xml_parser import XmlParser

# ------------------------------------------------------------------------------
class ParserError(Exception): pass
class TypeError(Exception): pass

# ParserError-related constants ------------------------------------------------
BAD_PARENT_ROW = 'For table "%s", you specified "%s" as parent table, but ' \
  'you referred to row number "%s" within the parent. This value must be a ' \
  'positive integer or zero (we start counting rows at 0).'
PARENT_NOT_FOUND = 'I cannot find table "%s" that you defined as being ' \
  'parent of "%s".'
TABLE_KEY_ERROR = 'Within a row of table "%s", you mention a column named ' \
  '"%s" which does not exist neither in "%s" itself, neither in its parent ' \
  'row(s). '
PARENT_ROW_NOT_FOUND = 'You specified table "%s" as inheriting from table ' \
  '"%s", row "%d", but this row does not exist (table "%s" as a length = %d). '\
  ' Note that we start counting rows at 0.'
PARENT_COLUMN_NOT_FOUND = 'You specified table "%s" as inheriting from table ' \
  '"%s", column "%s", but this column does not exist in table "%s" or parents.'
PARENT_ROW_COL_NOT_FOUND = 'You specified table "%s" as inheriting from ' \
  'table "%s", column "%s", value "%s", but it does not correspond to any ' \
  'row in table "%s".'
NO_ROWS_IN_TABLE_YET = 'In first row of table "%s", you use value \' " \' ' \
  'for referencing the cell value in previous row, which does not exist.'
VALUE_ERROR = 'Value error for column "%s" of table "%s". %s'
TYPE_ERROR = 'Type error for column "%s" of table "%s". %s'

# TypeError-related constants --------------------------------------------------
LIST_TYPE_ERROR = 'Maximum number of nested lists is 4.'
BASIC_TYPE_ERROR = 'Letter "%s" does not correspond to any valid type. ' \
  'Valid types are f (float), i (int), g (long) and b (bool).'
BASIC_VALUE_ERROR = 'Value "%s" can\'t be converted to type "%s".'
LIST_VALUE_ERROR = 'Value "%s" is malformed: within it, %s. You should check ' \
  'the use of separators ( , : ; - ) to obtain a schema conform to the type ' \
  '"%s".'

# ------------------------------------------------------------------------------
class Type:
    basicTypes = {'f': float, 'i':int, 'g':long, 'b':bool}
    separators = ['-', ';', ',', ':']

    def __init__(self, typeDecl):
        self.basicType = None # The python basic type
        self.listNumber = 0
        # If = 1 : it is a list. If = 2: it is a list of lists. If = 3...
        self.analyseTypeDecl(typeDecl)
        if self.listNumber > 4:
            raise TypeError(LIST_TYPE_ERROR)
        self.name = self.computeName()

    def analyseTypeDecl(self, typeDecl):
        for char in typeDecl:
            if char == 'l':
                self.listNumber += 1
            else:
                # Get the basic type
                if not (char in Type.basicTypes.keys()):
                    raise TypeError(BASIC_TYPE_ERROR % char)
                self.basicType = Type.basicTypes[char]
                break
        if not self.basicType:
            self.basicType = unicode

    def convertBasicValue(self, value):
        try:
            return self.basicType(value.strip())
        except ValueError:
            raise TypeError(BASIC_VALUE_ERROR % (value,
                                                 self.basicType.__name__))

    def convertValue(self, value):
        '''Converts a p_value which is a string into a value conform
        to self.'''
        if self.listNumber == 0:
            res = self.convertBasicValue(value)
        else:
            # Get separators in their order of appearance
            separators = []
            for char in value:
                if (char in Type.separators) and (char not in separators):
                    separators.append(char)            
            # Remove surplus separators
            if len(separators) > self.listNumber:
                nbOfSurplusSeps = len(separators) - self.listNumber
                separators = separators[nbOfSurplusSeps:]
            # If not enough separators, create corresponding empty lists.
            res = None
            innerList = None
            resIsComplete = False
            if len(separators) < self.listNumber:
                if not value:
                    res = []
                    resIsComplete = True
                else:
                    # Begin with empty list(s)
                    nbOfMissingSeps = self.listNumber - len(separators)
                    res = []
                    innerList = res
                    for i in range(nbOfMissingSeps-1):
                        newInnerList = []
                        innerList.append(newInnerList)
                        innerList = newInnerList
            # We can now convert the value
            separators.reverse()
            if innerList != None:
                innerList.append(self.convertListItem(value, separators))
            elif not resIsComplete:
                try:
                    res = self.convertListItem(value, separators)
                except TypeError, te:
                    raise TypeError(LIST_VALUE_ERROR % (value, te, self.name))
        return res

    def convertListItem(self, stringItem, remainingSeps):
        if not remainingSeps:
            res = self.convertBasicValue(stringItem)
        else:
            curSep = remainingSeps[0]
            tempRes = stringItem.split(curSep)
            if (len(tempRes) == 1) and (not tempRes[0]):
                # There was no value within value, so we produce an empty list.
                res = []
            else:
                res = []
                for tempItem in tempRes:
                    res.append(self.convertListItem(tempItem,
                                                    remainingSeps[1:]))
        return res

    def computeName(self):
        prefix = 'list of ' * self.listNumber
        return '<%s%s>' % (prefix, self.basicType.__name__)

    def __repr__(self): return self.name

# ------------------------------------------------------------------------------
class TableRow(UserDict.UserDict):
    def __init__(self, table):
        UserDict.UserDict.__init__(self)
        self.table = table

    def __getitem__(self, key):
        '''This method "implements" row inheritance: if the current row does
           not have an element with p_key, it looks in the parent row of this
           row, via the parent table self.table.'''
        # Return the value from this dict if present
        if self.has_key(key): return UserDict.UserDict.__getitem__(self, key)
        # Try to get the value from the parent row
        keyError = False
        t = self.table
        # Get the parent row
        if t.parent:
            if isinstance(t.parentRow, int):
                if t.parentRow < len(t.parent):
                    try:
                        res = t.parent[t.parentRow][key]
                    except KeyError:
                        keyError = True
                else:
                    raise ParserError(PARENT_ROW_NOT_FOUND % (t.name,
                      t.parent.name, t.parentRow, t.parent.name, len(t.parent)))
            else:
                tColumn, tValue = t.parentRow
                # Get the 1st row having tColumn = tValue
                rowFound = False
                for row in t.parent:
                    try:
                        curVal = row[tColumn]
                    except KeyError:
                        raise ParserError(PARENT_COLUMN_NOT_FOUND % (t.name,
                          t.parent.name, tColumn, t.parent.name))
                    if curVal == tValue:
                        rowFound = True
                        try:
                            res = row[key]
                        except KeyError:
                            keyError = True
                        break
                if not rowFound:
                    raise ParserError(PARENT_ROW_COL_NOT_FOUND % (t.name,
                      t.parent.name, tColumn, tValue, t.parent.name))
        else:
            keyError = True
        if keyError:
            raise KeyError(TABLE_KEY_ERROR % (t.name, key, t.name))
        return res

# ------------------------------------------------------------------------------
class Table(UserList.UserList):
    nameRex = re.compile('([^\(]+)(?:\((.*)\))?')

    def __init__(self):
        UserList.UserList.__init__(self)
        self.name = ''
        # Column names
        self.columns = []
        # Column types. If no type is defined for some column, value "None" will
        # be stored and wille correspond to default type "str".
        self.columnTypes = []
        # The parent table
        self.parent = None
        # The parent row, within the parent table
        self.parentRow = None

    def setName(self):
        '''Parses the table name and extracts from it the potential reference
           to a parent table.'''
        name = self.name.strip()
        elems = self.nameRex.search(name)
        name, parentSpec = elems.groups()
        self.name = name
        if parentSpec:
            res = parentSpec.split(':')
            if len(res) == 1:
                self.parent = parentSpec.strip()
                self.parentRow = 0
            else:
                self.parent = res[0].strip()
                res = res[1].split('=')
                if len(res) == 1:
                    try:
                        self.parentRow = int(res[0])
                    except ValueError:
                        msg = BAD_PARENT_ROW % (self.name, self.parent, res[0])
                        raise ParserError(msg)
                    if self.parentRow < 0:
                        msg = BAD_PARENT_ROW % (self.name, self.parent, res[0])
                        raise ParserError(msg)
                else:
                    self.parentRow = (res[0].strip(), res[1].strip())

    def addRow(self):
        '''Adds a row of data into this table, as a TableRow instance. This
           consists in converting the list of row data we have already added
           into the table into a TableRow instance.'''
        data = self[-1]
        row = TableRow(self)
        for i in range(len(self.columns)):
            column = self.columns[i]
            value = data[i].strip()
            if value == '"':
                # Check if a previous row exists
                if len(self) == 1:
                    raise ParserError(NO_ROWS_IN_TABLE_YET % self.name)
                value = self[-2][column]
            else:
                # Get the column type and convert the value to this type
                type = self.columnTypes[i]
                if type:
                    try:
                        value = type.convertValue(value)
                    except TypeError, te:
                        raise ParserError(VALUE_ERROR % (column, self.name, te))
            row[self.columns[i]] = value
        self[-1] = row

    def addColumn(self):
        '''A new column has been added into self.columns. Extract its type if
           defined.'''
        # Extract the parsed column name
        name = self.columns[-1].strip()
        type = None
        if ':' in name:
            # We have a type declaration
            name, typeDecl = name.split(':')
            try:
                type = Type(typeDecl.strip())
            except TypeError, te:
                raise ParserError(TYPE_ERROR % (name, self.name, te))
        # Update the lists of header names and types
        self.columns[-1] = name
        self.columnTypes.append(type)
        # Create a new empty column for the next one
        self.columns.append('')

    def dump(self, withContent=True):
        res = 'Table "%s"' % self.name
        if self.parent:
            res += ' extends table "%s"' % self.parent.name
            if isinstance(self.parentRow, int):
                res += '(%d)' % self.parentRow
            else:
                res += '(%s=%s)' % self.parentRow
        if withContent:
            res += '\n'
            for line in self:
                res += str(line)
        return res

    def instanceOf(self, tableName):
        res = False
        if self.parent:
            if self.parent.name == tableName:
                res = True
            else:
                res = self.parent.instanceOf(tableName)
        return res

    def asDict(self):
        '''If this table as only 2 columns named "key" and "value", it can be
        represented as a Python dict. This method produces this dict.'''
        infoDict = {}
        if self.parent:
            for info in self.parent:
              infoDict[info["key"]] = info["value"]
        for info in self:
            infoDict[info["key"]] = info["value"]
        return infoDict

# ------------------------------------------------------------------------------
class OdtTablesParser(XmlParser):
    PARSING = 0
    PARSING_TABLE_NAME = 1
    PARSING_TABLE_HEADERS = 2
    PARSING_DATA_ROW = 3

    def startDocument(self):
        XmlParser.startDocument(self)
        # Where to store the parsed tables, keyed by their names
        self.res = {}
        # The currently walked table
        self.currentTable = None
        # The currently walked data row, as list of strings (cell content)
        self.currentRow = None
        # The initial parsing state
        self.state = self.PARSING

    def startElement(self, elem, attrs):
        if elem == 'table:table':
            # A new table is encountered
            self.currentTable = Table()
        elif elem == 'table:table-row':
            if not self.currentTable.name:
                # This is the first row (table name)
                self.state = self.PARSING_TABLE_NAME
            elif not self.currentTable.columns:
                # This is the second row (column headers)
                self.state = self.PARSING_TABLE_HEADERS
                self.currentTable.columns.append('')
            else:
                # This is a data row
                self.state = self.PARSING_DATA_ROW
                self.currentTable.append([''])
        elif elem == 'table:table-cell':
            pass

    def endElement(self, elem):
        if elem == 'table:table':
            # Store the completelty parsed table in self.res
            table = self.currentTable
            self.res[table.name] = table
            self.currentTable = None
        elif elem == 'table:table-row':
            if self.state == self.PARSING_TABLE_NAME:
                # We have finished to parse the first row (table name)
                self.currentTable.setName()
                self.state = self.PARSING
            elif self.state == self.PARSING_TABLE_HEADERS:
                # We have finished to parse the second row
                del self.currentTable.columns[-1]
                self.state = self.PARSING
            elif self.state == self.PARSING_DATA_ROW:
                # We have finished parsing a data row
                del self.currentTable[-1][-1]
                self.currentTable.addRow()
                self.state = self.PARSING
        elif elem == 'table:table-cell':
            if self.state == self.PARSING_TABLE_HEADERS:
                # We have finished parsing a header value. Add a new one.
                self.currentTable.addColumn()
            elif self.state == self.PARSING_DATA_ROW:
                # We have finished parsing a cell value. Add a new one.
                self.currentTable[-1].append('')

    def characters(self, content):
        # Get the table name
        if self.state == self.PARSING_TABLE_NAME:
            self.currentTable.name += content
        elif self.state == self.PARSING_TABLE_HEADERS:
            self.currentTable.columns[-1] += content
        elif self.state == self.PARSING_DATA_ROW:
            self.currentTable[-1][-1] += content

    def endDocument(self):
        XmlParser.endDocument(self)

# ------------------------------------------------------------------------------
class TablesParser:
    def __init__(self, fileName, encoding=None):
        self.fileName = fileName
        # Parsed tables will be stored in this dict
        self.tables = None

    def linkTables(self):
        '''Resolve parend/child links between parsed tables'''
        for name, table in self.tables.iteritems():
            if not table.parent: continue
            if table.parent not in self.tables:
                raise ParserError(PARENT_NOT_FOUND % (table.parent, table.name))
            table.parent = self.tables[table.parent]

    def run(self):
        '''Unzip the ODT file and parse tables within content.xml'''
        # Create a folder in the OD temp folder
        folder = os.path.join(getOsTempFolder(), 'tables%f' % time.time())
        os.mkdir(folder)
        # Unzip the file in the OS temp folder
        unzip(self.fileName, folder)
        # Parse content.xml
        contentXml = os.path.join(folder, 'content.xml')
        self.tables = OdtTablesParser().parse(contentXml, source='file')
        # Revolve parent/child table links
        self.linkTables()
        # Delete the folder
        FolderDeleter.delete(folder)
        return self.tables
# ------------------------------------------------------------------------------
