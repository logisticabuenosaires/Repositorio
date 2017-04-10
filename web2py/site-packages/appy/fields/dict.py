# ------------------------------------------------------------------------------
# This file is part of Appy, a framework for building applications in the Python
# language. Copyright (C) 2007 Gaetan Delannay

# Appy is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation; either version 3 of the License, or (at your option) any later
# version.

# Appy is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU General Public License for more details.

# You should have received a copy of the GNU General Public License along with
# Appy. If not, see <http://www.gnu.org/licenses/>.

# ------------------------------------------------------------------------------
from appy import Object
from list import List
from appy.px import Px
from appy.gen.layout import Table

# ------------------------------------------------------------------------------
class Dict(List):
    '''A Dict value has the form ~{s_key: Object}~. Keys are fixed and given by
       a method specified in parameter "keys". Values are Object instances,
       whose attributes are determined by parameter "fields" that, similarly to
       the List field, determines sub-data for every entry in the dict. This
       field is build on top of the List field.'''

    # PX for rendering a single row
    pxRow = Px('''
     <tr valign="top" class=":loop.row.odd and 'even' or 'odd'">
      <x>:field.pxFirstCell</x>
      <td class="discreet">:row[1]</td>
      <td for="info in subFields" if="info[1]" align="center"
          var2="field=info[1];
                fieldName='%s*%s' % (field.name, rowId)">:field.pxRender</td>
     </tr>''')

    # PX for rendering the dict (shared between pxView and pxEdit)
    pxTable = Px('''
     <table var="isEdit=layoutType == 'edit'" if="isEdit or value"
            id=":'list_%s' % name" class="grid" width=":field.width"
            var2="keys=field.keys(obj);
                  subFields=field.getSubFields(zobj, layoutType)">
      <!-- Header -->
      <tr valign="bottom">
       <th width=":field.widths[0]"></th>
       <th for="info in subFields" if="info[1]"
           width=":field.widths[loop.info.nb+1]">::_(info[1].labelId)</th>
      </tr>
      <!-- Rows of data -->
      <x for="row in keys" var2="rowId=row[0]">:field.pxRow</x>
     </table>''')

    def __init__(self, keys, fields, validator=None, multiplicity=(0,1),
      default=None, show=True, page='main', group=None, layouts=None, move=0,
      specificReadPermission=False, specificWritePermission=False, width='',
      height=None, maxChars=None, colspan=1, master=None, masterValue=None,
      focus=False, historized=False, mapping=None, label=None,
      subLayouts=Table('frv', width=None), widths=None, view=None, xml=None):
        List.__init__(self, fields, validator, multiplicity, default, show,
          page, group, layouts, move, specificReadPermission,
          specificWritePermission, width, height, maxChars, colspan, master,
          masterValue, focus, historized, mapping, label, subLayouts, widths,
          view, xml)
        # Method in "keys" must return a list of tuples (key, title): "key"
        # determines the key that will be used to store the entry in the
        # database, while "title" will get the text that will be shown in the ui
        # while encoding/viewing this entry.
        # WARNING: a key must be a string, cannot contain digits only and
        # cannot contain char "*". A key is typically an object ID.
        self.keys = keys

    def computeWidths(self, widths):
        '''Set given p_widths or compute default ones if not given'''
        if not widths:
            self.widths = [''] * (len(self.fields) + 1)
        else:
            self.widths = widths

    def getStorableValue(self, obj, value):
        '''Gets p_value in a form that can be stored in the database'''
        res = {}
        for k, v in value.iteritems():
            res[k] = self.getStorableRowValue(obj, v)
        return res

    def remove(self, obj, key):
        '''Remove entry corresponding to p_key on the value stored on p_obj'''
        val = getattr(obj.o, self.name, None)
        if not val: return
        if key not in val: return
        del val[key]
        setattr(obj.o, self.name, val)

    def store(self, obj, value, overwrite=False):
        '''Stores the p_value (produced by m_getStorableValue) on p_obj. If some
           entry from p_value already exists in the DB value, it is updated,
           not overwritten.'''
        obj = obj.o
        if not self.persist: return
        dbValue = getattr(obj.aq_base, self.name, None)
        if not dbValue or overwrite:
            setattr(obj, self.name, value)
        else:
            # Update the DB value with p_value
            if not value: return
            for key, data in value.iteritems():
                if key not in dbValue:
                    dbValue[key] = data
                else:
                    dbValue[key].update(data)
            setattr(obj, self.name, dbValue)

    def subValidate(self, obj, value, errors):
        '''Validates inner fields'''
        for key, row in value.iteritems():
            for name, subField in self.fields:
                message = subField.validate(obj, getattr(row, name, None))
                if message:
                    setattr(errors, '%s*%s' % (subField.name, key), message)
# ------------------------------------------------------------------------------
