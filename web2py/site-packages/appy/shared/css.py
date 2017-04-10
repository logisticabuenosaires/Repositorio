# ------------------------------------------------------------------------------
import re
htmlColorNames = {
  'aliceblue': '#f0f8ff', 'antiquewhite': '#faebd7', 'aqua': '#00ffff',
  'aquamarine': '#7fffd4','azure': '#f0ffff', 'beige': '#f5f5dc',
  'bisque': '#ffe4c4', 'black': '#000000', 'blanchedalmond': '#ffebcd',
  'blue': '#0000ff', 'blueviolet': '#8a2be2', 'brown': '#a52a2a',
  'burlywood': '#deb887', 'cadetblue': '#5f9ea0', 'chartreuse': '#7fff00',
  'chocolate': '#d2691e', 'coral': '#ff7f50', 'cornflowerblue': '#6495ed',
  'cornsilk': '#fff8dc', 'crimson': '#dc143c', 'cyan': '#00ffff',
  'darkblue': '#00008b', 'darkcyan': '#008b8b', 'darkgoldenrod': '#b8860b',
  'darkgray': '#a9a9a9', 'darkgrey': '#a9a9a9', 'darkgreen': '#006400',
  'darkkhaki': '#bdb76b', 'darkmagenta': '#8b008b', 'darkolivegreen': '#556b2f',
  'darkorange': '#ff8c00', 'darkorchid': '#9932cc', 'darkred': '#8b0000',
  'darksalmon': '#e9967a', 'darkseagreen': '#8fbc8f', 'darkslateblue':'#483d8b',
  'darkslategray': '#2f4f4f', 'darkslategrey': '#2f4f4f',
  'darkturquoise': '#00ced1', 'darkviolet': '#9400d3', 'deeppink': '#ff1493',
  'deepskyblue': '#00bfff', 'dimgray': '#696969', 'dimgrey': '#696969',
  'dodgerblue': '#1e90ff', 'firebrick': '#b22222', 'floralwhite': '#fffaf0',
  'forestgreen': '#228b22', 'fuchsia': '#ff00ff', 'gainsboro': '#dcdcdc',
  'ghostwhite': '#f8f8ff', 'gold': '#ffd700', 'goldenrod': '#daa520',
  'gray': '#808080', 'grey': '#808080', 'green': '#008000',
  'greenyellow': '#adff2f', 'honeydew': '#f0fff0', 'hotpink': '#ff69b4',
  'indianred ': '#cd5c5c', 'indigo ': '#4b0082', 'ivory': '#fffff0',
  'khaki': '#f0e68c', 'lavender': '#e6e6fa', 'lavenderblush': '#fff0f5',
  'lawngreen': '#7cfc00', 'lemonchiffon': '#fffacd', 'lightblue': '#add8e6',
  'lightcoral': '#f08080', 'lightcyan': '#e0ffff',
  'lightgoldenrodyellow': '#fafad2', 'lightgray': '#d3d3d3',
  'lightgrey': '#d3d3d3', 'lightgreen': '#90ee90', 'lightpink': '#ffb6c1',
  'lightsalmon': '#ffa07a', 'lightseagreen': '#20b2aa',
  'lightskyblue': '#87cefa', 'lightslategray': '#778899',
  'lightslategrey': '#778899', 'lightsteelblue': '#b0c4de',
  'lightyellow': '#ffffe0', 'lime': '#00ff00', 'limegreen': '#32cd32',
  'linen': '#faf0e6', 'magenta': '#ff00ff', 'maroon': '#800000',
  'mediumaquamarine': '#66cdaa', 'mediumblue': '#0000cd',
  'mediumorchid': '#ba55d3', 'mediumpurple': '#9370db',
  'mediumseagreen': '#3cb371', 'mediumslateblue': '#7b68ee',
  'mediumspringgreen': '#00fa9a', 'mediumturquoise': '#48d1cc',
  'mediumvioletred': '#c71585', 'midnightblue': '#191970',
  'mintcream': '#f5fffa', 'mistyrose': '#ffe4e1', 'moccasin': '#ffe4b5',
  'navajowhite': '#ffdead', 'navy': '#000080', 'oldlace': '#fdf5e6',
  'olive': '#808000', 'olivedrab': '#6b8e23', 'orange': '#ffa500',
  'orangered': '#ff4500', 'orchid': '#da70d6', 'palegoldenrod': '#eee8aa',
  'palegreen': '#98fb98', 'paleturquoise': '#afeeee','palevioletred': '#db7093',
  'papayawhip': '#ffefd5', 'peachpuff': '#ffdab9', 'peru': '#cd853f',
  'pink': '#ffc0cb', 'plum': '#dda0dd', 'powderblue': '#b0e0e6',
  'purple': '#800080', 'rebeccapurple': '#663399', 'red': '#ff0000',
  'rosybrown': '#bc8f8f', 'royalblue': '#4169e1', 'saddlebrown': '#8b4513',
  'salmon': '#fa8072', 'sandybrown': '#f4a460', 'seagreen': '#2e8b57',
  'seashell': '#fff5ee', 'sienna': '#a0522d', 'silver': '#c0c0c0',
  'skyblue': '#87ceeb', 'slateblue': '#6a5acd', 'slategray': '#708090',
  'slategrey': '#708090', 'snow': '#fffafa', 'springgreen': '#00ff7f',
  'steelblue': '#4682b4', 'tan': '#d2b48c', 'teal': '#008080',
  'thistle': '#d8bfd8', 'tomato': '#ff6347', 'turquoise': '#40e0d0',
  'violet': '#ee82ee', 'wheat': '#f5deb3', 'white': '#ffffff',
  'whitesmoke': '#f5f5f5', 'yellow': '#ffff00', 'yellowgreen': '#9acd32'}
# ------------------------------------------------------------------------------
def parseStyleAttribute(value, asDict=False):
    '''Returns a list of CSS (name, value) pairs (or a dict if p_asDict is
       True), parsed from p_value, which holds the content of a HTML "style"
       tag.'''
    if asDict: res = {}
    else:      res = []
    for attr in value.split(';'):
        if not attr.strip(): continue
        name, value = attr.split(':', 1)
        if asDict: res[name.strip()] = value.strip()
        else:      res.append( (name.strip(), value.strip()) )
    return res

# ------------------------------------------------------------------------------
class CssValue:
    '''Represents a CSS value'''
    # CSS properties having a unit, with their default unit
    unitProperties = {'width': 'px', 'height': 'px', 'margin-left': 'px',
      'margin-right': 'px', 'margin-top': 'px', 'margin-bottom': 'px',
      'text-indent': 'px', 'font-size': None, 'border-spacing': 'px'}
    # CSS properties defining colors
    colorProperties = ('color', 'background-color')
    # Regular expressions for parsing (parts of) CSS values
    valueRex = re.compile('(-?\d*(?:\.\d+)?)(%|px|cm|pt)?')
    rgbRex = re.compile('rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)')

    def __init__(self, name, value):
        # p_value can be another CssValue instance
        if isinstance(value, CssValue):
            self.value = value.value
            self.unit = value.unit
            return
        # If we are here, p_value is a string
        self.unit = None
        value = value.strip().lower()
        if name in CssValue.unitProperties:
            value, unit = CssValue.valueRex.match(value).groups()
            self.value = int(round(float(value)))
            self.unit = unit or CssValue.unitProperties[name]
        elif name in CssValue.colorProperties:
            if value.startswith('#'):
                self.value = value # Hexadecimal, keep it as is
            elif value.startswith('rgb('):
                # Convert the RGB value to hexadecimal
                self.value = self.rgb2hex(value)
            else:
                # Probably a color name. Convert it to hexadecimal.
                self.value = htmlColorNames.get(value, value)
        else:
            self.value = value

    def rgb2hex(self, value):
        '''Converts a color expressed in RGB to hexadecimal'''
        match = CssValue.rgbRex.match(value)
        # If we couldn't parse the value, left it untouched
        if not match: return value
        res = '#'
        for val in match.groups():
            hexa = hex(int(val))[2:].upper() # Remove prefix "0x"
            res += hexa
        return res

    def __str__(self):
        res = str(self.value)
        if self.unit: res += self.unit
        return res

    def __repr__(self): return self.__str__()

class CssStyles:
    '''This class represents a set of styles collected from:
       * an HTML "style" attribute;
       * other attributes like "width".
    '''
    # The correspondance between xhtml attributes and CSS properties. within
    # CSS property names, dashes have bee removed because they are used as names
    # for Python instance attributes.
    xhtml2css = {'width': 'width', 'height': 'height', 'align': 'text-align',
                 'cellspacing': 'border-spacing', 'border': 'border'}

    def __init__(self, elem, attrs):
        '''Analyses styles as found in p_attrs and sets, for every found style,
           an attribute on self.'''
        # In priority, parse the "style" attribute if present
        if attrs.has_key('style'):
            styles = parseStyleAttribute(attrs['style'], asDict=True)
            for name, value in styles.iteritems():
                setattr(self, name.replace('-', ''), CssValue(name, value))
        # Parse obsolete XHTML style-related attributes if present. But they
        # will not override corresponding attributes from the "styles"
        # attributes if found.
        for xhtmlName, cssName in self.xhtml2css.iteritems():
            name = cssName.replace('-', '')
            if not hasattr(self, name) and attrs.has_key(xhtmlName):
                setattr(self, name, CssValue(cssName, attrs[xhtmlName]))

    def __repr__(self):
        res = '<CSS'
        for name, value in self.__dict__.iteritems():
            res += ' %s:%s' % (name, value)
        return res + '>'

    def __nonzero__(self): return len(self.__dict__) > 0
    def get(self): return self.__dict__
# ------------------------------------------------------------------------------
