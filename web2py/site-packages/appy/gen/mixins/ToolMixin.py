# ------------------------------------------------------------------------------
import os, os.path, sys, re, time, random, types, base64, urllib
from appy import Object
import appy.gen
from appy.gen import Search, UiSearch, String, Page
from appy.gen.layout import ColumnLayout
from appy.gen import utils as gutils
from appy.gen.mixins import BaseMixin
from appy.gen.wrappers import AbstractWrapper
from appy.gen.descriptors import ClassDescriptor
from appy.gen.navigate import Siblings
from appy.shared import mimeTypes
from appy.shared import utils as sutils
from appy.shared.data import languages
from appy.shared.ldap_connector import LdapConnector
try:
    from AccessControl.ZopeSecurityPolicy import _noroles
except ImportError:
    _noroles = []

# Global JS internationalized messages that will be computed in every page -----
jsMessages = ('no_elem_selected', 'action_confirm', 'save_confirm',
              'warn_leave_form')

# Error messages ---------------------------------------------------------------
USER_NOT_FOUND = 'User %s not found. Probably a problem implying several ' \
                 'Appy apps put behind the same domain name or dev machine.'
PAGE_NOT_FOUND = '404: %s not found.'
PAGE_UNAUTHORIZED = 'unauthorized access to %s.'

# ------------------------------------------------------------------------------
class ToolMixin(BaseMixin):
    _appy_meta_type = 'Tool'
    xhtmlEncoding = 'text/html;charset=UTF-8'

    def getPortalType(self, metaTypeOrAppyClass):
        '''Returns the name of the portal_type that is based on
           p_metaTypeOrAppyClass.'''
        appName = self.getProductConfig().PROJECTNAME
        res = metaTypeOrAppyClass
        if not isinstance(metaTypeOrAppyClass, basestring):
            res = gutils.getClassName(metaTypeOrAppyClass, appName)
        if res.find('_wrappers') != -1:
            elems = res.split('_')
            res = '%s%s' % (elems[1], elems[4])
        if res in ('User', 'Group', 'Translation'): res = appName + res
        return res

    def home(self):
        '''Returns the content of px ToolWrapper.pxHome'''
        tool = self.appy()
        return tool.pxHome({'obj': None, 'tool': tool})

    def query(self):
        '''Returns the content of px ToolWrapper.pxQuery'''
        tool = self.appy()
        return tool.pxQuery({'obj': None, 'tool': tool})

    def search(self):
        '''Returns the content of px ToolWrapper.pxSearch'''
        tool = self.appy()
        return tool.pxSearch({'obj': None, 'tool': tool})

    def getHomePage(self):
        '''Return the home page when a user hits the app'''
        # If the app defines a method "getHomePage", call it
        tool = self.appy()
        url = None
        try:
            url = tool.getHomePage()
        except AttributeError:
            pass
        if not url:
            # Bring Managers to the config, lead others to pxHome
            user = self.getUser()
            if not user:
                raise Exception(USER_NOT_FOUND % self.identifyUser()[0])
            if user.has_role('Manager'):
                url = self.absolute_url()
            else:
                url = '%s/home' % self.absolute_url()
        # Does the user come to its home page for authenticating and,
        # afterwards, being redirected to some other page?
        gotoUrl = self.REQUEST.get('goto')
        if gotoUrl:
            gotoUrl = urllib.quote(gotoUrl)
            if '?' in url: url += '&goto=%s' % gotoUrl
            else: url += '?goto=%s' % gotoUrl
            self.say(self.translate('please_authenticate'))
        return url

    def getErrorPage(self, options):
        '''Gets the error page'''
        req = self.REQUEST
        # Add Appy-specific context
        tool = self.appy()
        options['obj'] = None
        options['tool'] = tool
        errorType = options['error_type']
        # Manage the special case of inner errors produced by pod buffers
        if errorType == 'EvaluationError':
            errorType = options['error_value'].originalError.__class__.__name__
        url = req['AUTHENTICATION_PATH'] or req['PATH_INFO']
        # When called from a Ajax request, avoid displaying the whole page,
        # with banner, etc: simulate a popup.
        if url.endswith('/ajax'): req['popup'] = '1'
        params = req['QUERY_STRING']
        if params: url += '?%s' % params
        # Manage the various kinds of errors
        if errorType == 'NotFound':
            # Return a 404 page
            options['msg'] = self.translate('not_found')
            self.log(PAGE_NOT_FOUND % url, type='warning')
            return tool.px404(options).encode('utf-8')
        elif errorType == 'Unauthorized':
            if self.getUser().login == 'anon':
                # Let the user authenticate himself
                url = '%s?goto=%s' % (self.getSiteUrl(), urllib.quote(url))
                return self.goto(url, msg='Please authenticate')
            else:
                # Return a specific error page
                options['msg'] = self.translate('unauthorized')
                self.log(PAGE_UNAUTHORIZED % url, type='warning')
                return tool.px403(options).encode('utf-8')
        else:
            # Return the standard error page
            if errorType == 'MessageException':
                # Display a nice and not a technical error message
                options['msg'] = str(options['error_value'])
                options['showTraceback'] = False
            else:
                options['msg'] = self.translate('server_error')
                # Integrate the traceback if the user is admin
                self.log(sutils.Traceback.get(), type='error')
                options['showTraceback'] = True
            return tool.px500(options).encode('utf-8')

    def getHomeObject(self, inPopup=False):
        '''The concept of "home object" is the object where the user must "be",
           even if he is "nowhere". For example, if the user is on a search
           screen, there is no contextual object. In this case, if we have a
           home object for him, we will use it as contextual object, and its
           portlet menu will nevertheless appear: the user will not have the
           feeling of being lost.'''
        # If we are in the popup, we do not want any home object in the way.
        if inPopup: return
        # If the app defines a method "getHomeObject", call it.
        try:
            return self.appy().getHomeObject()
        except AttributeError:
            # For managers, the home object is the config. For others, there is
            # no default home object.
            user = self.getUser()
            if not user:
                # On heavy load, user could be None
                self.log('No user on Tool::getHomeObject', type='error')
                return
            if user.has_role('Manager'): return self.appy()

    def getPageTitle(self, obj):
        '''Returns content for tag html->head->title'''
        # The page title is based on the p_obj title
        res = (obj and (obj != self)) and obj.getShownValue() or \
              self.translate('app_name')
        # Ensure this is a string
        if not isinstance(res, basestring): res = str(res)
        # Remove <br/> tags
        if '<br/>' in res: res = res[:res.index('<br/>')]
        # Add the page title if found
        if obj and ('page' in self.REQUEST):
            pageLabel = '%s_page_%s' % (obj.meta_type, self.REQUEST['page'])
            text = self.translate(pageLabel, blankOnError=True)
            if text:
                if res: res += ' :: '
                res += text
        return self.truncateValue(res, width=100)

    def getCatalog(self):
        '''Returns the catalog object'''
        return self.getParentNode().catalog

    def getCatalogValue(self, obj, indexName):
        '''Get, for p_obj, the value stored in the catalog for the index
           named p_indexName.'''
        catalogBrain = self.getObject(obj.id, brain=True)
        catalog = self.getApp().catalog
        index = catalog.Indexes[indexName]
        indexType = index.getTagName()
        if indexType == 'ZCTextIndex':
            # Zope bug: the lexicon can't be retrieved correctly
            index._v_lexicon = getattr(catalog, index.lexicon_id)
        res = index.getEntryForObject(catalogBrain.getRID())
        if indexType == 'DateIndex':
            # The index value is a number. Add a DateTime representation too.
            if not res: res = ''
            else:
                from appy.fields.date import getDateFromIndexValue
                res = '%d (%s)' % (res, getDateFromIndexValue(res))
        return res

    def getApp(self):
        '''Returns the root Zope object'''
        return self.getPhysicalRoot()

    def getSiteUrl(self):
        '''Returns the absolute URL of this site'''
        return self.getApp().absolute_url()

    def getIncludeUrl(self, name, bg=False):
        '''Gets the full URL of an external resource, like an image, a
           Javascript or a CSS file, named p_name. If p_bg is True, p_name is
           an image that is meant to be used in a "style" attribute for defining
           the background image of some XHTML tag.'''
        # If no extension is found in p_name, we suppose it is a png image
        if '.' not in name: name += '.png'
        url = '%s/ui/%s' % (self.getPhysicalRoot().absolute_url(), name)
        if not bg: return url
        return 'background-image: url(%s)' % url

    def doPod(self):
        '''Performs an action linked to a pod field: generate, freeze,
           unfreeze... a document from a pod field.'''
        rq = self.REQUEST
        # Get the object that is the target of this action. On heavy load,
        # request keys "objectUid" and "fieldName" may not be present.
        objectId = rq.get('objectUid')
        if not objectId:
            self.log('Wrong doPod request (no object ID)', type='error')
            return
        obj = self.getObject(objectId, appy=True)
        fieldName = rq.get('fieldName')
        if not fieldName:
            self.log('Wrong doPod request (no field name)', type='error')
            return
        return obj.getField(fieldName).onUiRequest(obj, rq)

    def getAppName(self):
        '''Returns the name of the application'''
        return self.getProductConfig().PROJECTNAME

    def getPath(self, path):
        '''Returns the folder or object whose absolute path p_path.'''
        res = self.getPhysicalRoot()
        if path == '/': return res
        path = path[1:]
        if '/' not in path: return res._getOb(path) # For performance
        for elem in path.split('/'): res = res._getOb(elem)
        return res

    def showLanguageSelector(self):
        '''We must show the language selector if the app config requires it and
           it there is more than 2 supported languages. Moreover, on some pages,
           switching the language is not allowed.'''
        cfg = self.getProductConfig(True)
        if not cfg.languageSelector or cfg.forcedLanguage: return
        if len(cfg.languages) < 2: return
        page = self.REQUEST.get('ACTUAL_URL').split('/')[-1]
        return page not in ('edit', 'query', 'search', 'do')

    def showForgotPassword(self):
        '''We must show link "forgot password?" when the app requires it.'''
        return self.getProductConfig(True).activateForgotPassword

    def getLanguages(self):
        '''Returns the supported languages. First one is the default.'''
        return self.getProductConfig(True).languages

    def getLanguageName(self, code, lowerize=False):
        '''Gets the language name (in this language) from a 2-chars language
           p_code.'''
        res = languages.get(code)[2]
        if not lowerize: return res
        return res.lower()

    def changeLanguage(self):
        '''Sets the language cookie with the new desired language code that is
           in request["language"].'''
        rq = self.REQUEST
        rq.RESPONSE.setCookie('_ZopeLg', rq['language'], path='/')
        return self.goto(self.getReferer())

    def flipLanguageDirection(self, align, dir):
        '''According to language direction p_dir ('ltr' or 'rtl'), this method
           turns p_align from 'left' to 'right' (or the inverse) when
           required.'''
        if dir == 'ltr': return align
        if align == 'left': return 'right'
        if align == 'right': return 'left'
        return align

    def getGlobalCssJs(self, dir):
        '''Returns the list of CSS and JS files to include in the main template.
           The method ensures that appy.css and appy.js come first. If p_dir
           (=language *dir*rection) is "rtl" (=right-to-left), the stylesheet
           for rtl languages is also included.'''
        names = self.getPhysicalRoot().ui.objectIds('File')
        # The single Appy Javascript file
        names.remove('appy.js'); names.insert(0, 'appy.js')
        # CSS changes for left-to-right languages
        names.remove('appyrtl.css')
        if dir == 'rtl': names.insert(0, 'appyrtl.css')
        names.remove('appy.css'); names.insert(0, 'appy.css')
        return names

    def consumeMessages(self, unlessRedirect=False):
        '''Returns the list of messages to show to a web page and clean it in
           the session.'''
        # Do not consume anything if p_unlessRedirect is True and we are
        # redirecting the user.
        resp = self.REQUEST.RESPONSE
        if unlessRedirect and ('appy-redirect' in resp.headers): return
        rq = self.REQUEST
        res = rq.SESSION.get('messages', '')
        if res:
            del rq.SESSION['messages']
            res = ' '.join([m[1] for m in res])
        return res

    def getRootClasses(self):
        '''Returns the list of root classes for this application'''
        cfg = self.getProductConfig().appConfig
        rootClasses = cfg.rootClasses
        if rootClasses == None: return [] # No root class at all
        if not rootClasses:
            # We consider every class as being a root class
            rootClasses = self.getProductConfig().appClassNames
        return [self.getAppyClass(k) for k in rootClasses]

    def getSearchInfo(self, className, refInfo=None):
        '''Returns, as an object:
           - the list of searchable fields (some among all indexed fields);
           - the number of columns for layouting those fields.'''
        fields = []
        if refInfo:
            # The search is triggered from a Ref field
            refObject, fieldName = self.getRefInfo(refInfo)
            refField = refObject.getAppyType(fieldName)
            fieldNames = refField.queryFields or ()
            nbOfColumns = refField.queryNbCols
        else:
            # The search is triggered from an app-wide search
            klass = self.getAppyClass(className)
            fieldNames = getattr(klass, 'searchFields', None)
            if callable(fieldNames): fieldNames = fieldNames(self.appy())
            if not fieldNames:
                # Gather all the indexed fields on this class
                fieldNames = [f.name for f in self.getAllAppyTypes(className) \
                              if f.indexed]
                # Put SearchableText in front of the list and ensure "title"
                # is not there
                if 'title' in fieldNames: fieldNames.remove('title')
                st = 'SearchableText'
                if st in fieldNames: fieldNames.remove(st)
                fieldNames.insert(0, st)
            nbOfColumns = getattr(klass, 'numberOfSearchColumns', 3)
        for name in fieldNames:
            field = self.getAppyType(name, className=className)
            fields.append(field)
        return Object(fields=fields, nbOfColumns=nbOfColumns)

    def showPortlet(self, obj, layoutType):
        '''When must the portlet be shown? p_obj and p_layoutType can be None
           if we are not browing any objet (ie, we are on the home page).'''
        # Not on 'edit' pages or if there is no root class
        classes = self.getProductConfig(True).rootClasses
        if not classes or (layoutType == 'edit'): return
        res = True
        if obj and hasattr(obj, 'showPortlet'):
            res = obj.showPortlet()
        else:
            tool = self.appy()
            if hasattr(tool, 'showPortletAt'):
                res = tool.showPortletAt(self.REQUEST['ACTUAL_URL'])
        return res

    def getObject(self, uid, appy=False, brain=False, temp=False):
        '''Allows to retrieve an object from its p_uid. p_brain and p_temp
           cannot be both True'''
        app = self.getPhysicalRoot()
        if not temp:
            res = app.catalog(UID=uid)
            if not res: return
            res = res[0]
            if brain: return res
            res = res._unrestrictedGetObject()
        else:
            res = getattr(app.temp_folder, uid)
        if not appy: return res
        return res.appy()

    def getAllowedValue(self):
        '''Gets, for the current user, the value of index "Allowed".'''
        user = self.getUser()
        # Get the user roles. If we do not make a copy of the list here, we will
        # really add user logins among user roles!
        res = user.getRoles()[:]
        # Get the user logins
        if user.login != 'anon':
            for login in user.getLogins():
                res.append('user:%s' % login)
        return res

    def executeQuery(self, className, searchName=None, startNumber=0,
                     search=None, remember=False, brainsOnly=False,
                     maxResults=None, noSecurity=False, sortBy=None,
                     sortOrder='asc', filterKey=None, filterValue=None,
                     refObject=None, refField=None):
        '''Executes a query on instances of a given p_className in the catalog.
           If p_searchName is specified, it corresponds to:
             1) a search defined on p_className: additional search criteria
                will be added to the query, or;
             2) "customSearch": in this case, additional search criteria will
                also be added to the query, but those criteria come from the
                session (in key "searchCriteria") and came from pxSearch.

           We will retrieve objects from p_startNumber. If p_search is defined,
           it corresponds to a custom Search instance (instead of a predefined
           named search like in p_searchName). If both p_searchName and p_search
           are given, p_search is ignored.

           This method returns a list of objects in the form of an instance of
           SomeObjects (see in appy.gen.utils). If p_brainsOnly is True, it
           returns a list of brains instead (can be useful for some usages like
           knowing the number of objects without needing to get information
           about them). If no p_maxResults is specified, the method returns
           maximum self.numberOfResultsPerPage. The method returns all objects
           if p_maxResults equals string "NO_LIMIT".

           If p_noSecurity is True, it gets all the objects, even those that the
           currently logged user can't see.

           The result is sorted according to the potential sort key defined in
           the Search instance (Search.sortBy, together with Search.sortOrder).
           But if parameter p_sortBy is given, it defines or overrides the sort.
           In this case, p_sortOrder gives the order (*asc*ending or
           *desc*ending).

           If p_filterKey is given, it represents an additional search parameter
           to take into account: the corresponding search value is in
           p_filterValue.

           If p_refObject and p_refField are given, the query is limited to the
           objects that are referenced from p_refObject through p_refField.'''
        params = {'ClassName': className}
        klass = self.getAppyClass(className, wrapper=True)
        if not brainsOnly: params['batch'] = True
        # Manage additional criteria from a search when relevant
        if searchName: search = self.getSearch(className, searchName)
        if search:
            # Add in params search and sort criteria
            search.updateSearchCriteria(params, klass)
        # Determine or override sort if specified
        if sortBy:
            params['sort_on'] = Search.getIndexName(sortBy, klass, usage='sort')
            params['sort_order'] = (sortOrder == 'desc') and 'reverse' or None
        # If defined, add the filter among search parameters
        if filterKey:
            filterKey = Search.getIndexName(filterKey, klass)
            filterValue = Search.getSearchValue(filterKey, filterValue, klass)
            params[filterKey] = filterValue
            # TODO This value needs to be merged with an existing one if already
            # in params, or, in a first step, we should avoid to display the
            # corresponding filter widget on the screen.
        if refObject:
            refField = refObject.getAppyType(refField)
            params['UID'] = getattr(refObject, refField.name).data
        # Use index "Allowed" if noSecurity is False
        if not noSecurity: params['Allowed'] = self.getAllowedValue()
        brains = self.getPath("/catalog")(**params)
        # Compute maxResults
        if not maxResults:
            if refField: maxResults = refField.maxPerPage
            else: maxResults = search.maxPerPage or \
                               self.appy().numberOfResultsPerPage
        elif maxResults == 'NO_LIMIT':
            maxResults = None
        # Return brains only if required
        if brainsOnly:
            if not maxResults: return brains
            else: return brains[:maxResults]
        res = gutils.SomeObjects(brains, maxResults, startNumber,
                                 noSecurity=noSecurity)
        res.brainsToObjects()
        # In some cases (p_remember=True), we need to keep some information
        # about the query results in the current user's session, allowing him
        # to navigate within elements without re-triggering the query every
        # time a page for an element is consulted.
        if remember:
            if not searchName:
                if not search:
                    searchName = className
                else:
                    searchName = search.getSessionKey(className, full=False)
            uids = {}
            i = -1
            for obj in res.objects:
                i += 1
                uids[startNumber+i] = obj.id
            self.REQUEST.SESSION['search_%s' % searchName] = uids
        return res

    def getResultColumnsLayouts(self, className, refInfo):
        '''Returns the column layouts for displaying objects of
           p_className.'''
        if refInfo[0]:
            return refInfo[0].getAppyType(refInfo[1]).shownInfo
        else:
            k = self.getAppyClass(className)
            if not hasattr(k, 'listColumns'): return ('title',)
            if callable(k.listColumns): return k.listColumns(self.appy())
            return k.listColumns

    def getResultCss(self, className, layoutType='view'):
        '''Returns the CSS class(es) to apply when displaying a table containing
           instances of class named p_className.'''
        k = self.getAppyClass(className)
        if hasattr(k, 'listCss'): return k.listCss
        if layoutType == 'cell': return 'list'
        return 'list compact'

    def truncateValue(self, value, width=20):
        '''Truncates the p_value according to p_width. p_value has to be
           unicode-encoded for being truncated (else, one char may be spread on
           2 chars).'''
        # Param p_width can be None
        if not width: width = 20
        if isinstance(value, str): value = value.decode('utf-8')
        if len(value) > width:
            value = value[:width] + u'...'
        return value.encode('utf-8')

    def truncateText(self, text, width=20):
        '''Truncates p_text to max p_width chars. If the text is longer than
           p_width, the truncated part is put in a "acronym" html tag. p_text
           has to be unicode-encoded for being truncated (else, one char may be
           spread on 2 chars).'''
        # Param p_width can be None
        if not width: width = 20
        if isinstance(text, str): text = text.decode('utf-8')
        if len(text) > width:
            text = u'<acronym title="%s">%s...</acronym>' % (text, text[:width])
        return text.encode('utf-8')

    def splitList(self, l, sub):
        '''Returns a list made of the same elements as p_l, but grouped into
           sub-lists of p_sub elements.'''
        return sutils.splitList(l, sub)

    def quote(self, s, escapeWithEntity=True):
        '''Returns the quoted version of p_s.'''
        if not isinstance(s, basestring): s = str(s)
        repl = escapeWithEntity and '&apos;' or "\\'"
        s = s.replace('\r\n', '').replace('\n', '').replace("'", repl)
        return "'%s'" % s

    def getLayoutType(self):
        '''Guess the current layout type, according to actual URL.'''
        url = self.REQUEST['ACTUAL_URL']
        if url.endswith('/view'): return 'view'
        if url.endswith('/edit') or url.endswith('/do'): return 'edit'

    def getZopeClass(self, name):
        '''Returns the Zope class whose name is p_name.'''
        exec 'from Products.%s.%s import %s as C'% (self.getAppName(),name,name)
        return C

    def getAppyClass(self, zopeName, wrapper=False):
        '''Gets the Appy class corresponding to the Zope class named p_name.
           If p_wrapper is True, it returns the Appy wrapper. Else, it returns
           the user-defined class.'''
        # p_zopeName may be the name of the Zope class *or* the name of the Appy
        # class (shorter, not prefixed with the underscored package path).
        classes = self.getProductConfig().allShortClassNames
        if zopeName in classes: zopeName = classes[zopeName]
        zopeClass = self.getZopeClass(zopeName)
        if wrapper: return zopeClass.wrapperClass
        else: return zopeClass.wrapperClass.__bases__[-1]

    def getAllClassNames(self):
        '''Returns the name of all classes within this app, including default
           Appy classes (Tool, Translation, Page, etc).'''
        return self.getProductConfig().allClassNames + [self.__class__.__name__]

    def getCreateMeans(self, klass):
        '''Gets the different ways objects of p_klass can be created: via a
           web form ("form") and/or via templates (a Search instance), or None
           (only programmatically). Result is an Object instance.'''
        # By default, instances are created via an empty web form
        if not klass.__dict__.has_key('create'): return Object(means=['form'])
        res = Object(means=[])
        means = klass.create
        if not means: return res # Create objects programmatically only
        tool = self.appy()
        if callable(means): means = means(tool)
        if not means: return res
        for mean in means:
            if mean == 'form':
                res.means.append(mean)
            elif isinstance(mean, Search):
                res.means.append('template')
                res.search = mean
                res.link = '%s/query?className=%s&search=fromSearch&popup=1&' \
                  'fromClass=%s' % (tool.url, self.getPortalType(mean.klass),
                                    self.getPortalType(klass))
        return res

    def userMaySearch(self, klass):
        '''May the user search among instances of root p_klass ?'''
        # When editing a form, one should avoid annoying the user with this
        url = self.REQUEST['ACTUAL_URL']
        if url.endswith('/edit') or url.endswith('/do'): return
        if hasattr(klass, 'maySearch'): return klass.maySearch(self.appy())
        return True

    def userMayCreate(self, klass):
        '''May the logged user create instances of p_klass ? This information
           can be defined on p_klass, in static attribute "creators".
           1. If this attr holds a list, we consider it to be a list of roles,
              and we check that the user has at least one of those roles.
           2. If this attr holds a boolean, we consider that the user can create
              instances of this class if the boolean is True.
           3. If this attr stores a method, we execute the method, and via its
              result, we fall again in cases 1 or 2.

           If p_klass does not define this attr "creators", we will use a
           default list of roles as defined in the config.'''
        # Get the value of attr "creators", or a default value if not present
        if hasattr(klass, 'creators'):
            creators = klass.creators
        else:
            creators = self.getProductConfig().appConfig.defaultCreators
        # Resolve case (3): if "creators" is a method, execute it.
        if callable(creators): creators = creators(self.appy())
        # Resolve case (2)
        if isinstance(creators, bool) or not creators: return creators
        # Resolve case (1): checks whether the user has at least one of the
        # roles listed in "creators".
        for role in self.getUser().getRoles():
            if role in creators:
                return True

    def subTitleIsUsed(self, className):
        '''Does class named p_className define a method "getSubTitle"?'''
        klass = self.getAppyClass(className)
        return hasattr(klass, 'getSubTitle')

    def _searchValueIsEmpty(self, key):
        '''Returns True if request value in key p_key can be considered as
           empty.'''
        rq = self.REQUEST.form
        if key.endswith('*int') or key.endswith('*float'):
            # We return True if "from" AND "to" values are empty.
            toKey = '%s_to' % key[2:key.find('*')]
            return not rq[key].strip() and not rq[toKey].strip()
        elif key.endswith('*date'):
            # We return True if "from" AND "to" values are empty. A value is
            # considered as not empty if at least the year is specified.
            toKey = '%s_to_year' % key[2:-5]
            return not rq[key] and not rq[toKey]
        else:
            return not rq[key]

    def _getDateTime(self, year, month, day, setMin):
        '''Gets a valid DateTime instance from date information coming from the
           request as strings in p_year, p_month and p_day. Returns None if
           p_year is empty. If p_setMin is True, when some
           information is missing (month or day), we will replace it with the
           minimum value (=1). Else, we will replace it with the maximum value
           (=12, =31).'''
        if not year: return None
        if not month:
            if setMin: month = 1
            else:      month = 12
        if not day:
            if setMin: day = 1
            else:      day = 31
        DateTime = self.getProductConfig().DateTime
        # Set the hour
        if setMin: hour = '00:00'
        else: hour = '23:59'
        # We loop until we find a valid date. For example, we could loop from
        # 2009/02/31 to 2009/02/28.
        dateIsWrong = True
        while dateIsWrong:
            try:
                res = DateTime('%s/%s/%s %s' % (year, month, day, hour))
                dateIsWrong = False
            except:
                day = int(day)-1
        return res

    def _getDefaultSearchCriteria(self):
        '''We are about to perform an advanced search on instances of a given
           class. Check, on this class, if in field Class.searchAdvanced, some
           default criteria (field values, sort filters, etc) exist, and, if
           yes, return it.'''
        res = {}
        rq = self.REQUEST
        if 'className' not in rq.form: return res
        klass = self.getAppyClass(rq.form['className'])
        if not hasattr(klass, 'searchAdvanced'): return res
        # In klass.searchAdvanced, we have the Search instance representing
        # default advanced search criteria.
        wrapperClass = self.getAppyClass(rq.form['className'], wrapper=True)
        klass.searchAdvanced.updateSearchCriteria(res, wrapperClass,
                                                  advanced=True)
        return res

    transformMethods = {'uppercase': 'upper', 'lowercase': 'lower',
                        'capitalize': 'capitalize'}
    def storeSearchCriteria(self):
        '''Stores the search criteria coming from the request into the
           session.'''
        rq = self.REQUEST
        # Store the search criteria in the session
        criteria = self._getDefaultSearchCriteria()
        for name in rq.form.keys():
            if name.startswith('w_') and not self._searchValueIsEmpty(name):
                hasStar = name.find('*') != -1
                fieldName = not hasStar and name[2:] or name[2:name.find('*')]
                field = self.getAppyType(fieldName, rq.form['className'])
                if field and not field.persist and not field.indexed: continue
                # We have a(n interval of) value(s) that is not empty for a
                # given field or index.
                value = rq.form[name]
                if hasStar:
                    value = value.strip()
                    # The type of the value is encoded after char "*".
                    name, type = name.split('*')
                    if type == 'bool':
                        exec 'value = %s' % value
                    elif type in ('int', 'float'):
                        # Get the "from" value
                        if not value: value = None
                        else:
                            exec 'value = %s(value)' % type
                        # Get the "to" value
                        toValue = rq.form['%s_to' % name[2:]].strip()
                        if not toValue: toValue = None
                        else:
                            exec 'toValue = %s(toValue)' % type
                        if value != toValue:
                            value = (value, toValue)
                    elif type == 'date':
                        prefix = name[2:]
                        # Get the "from" value
                        year  = value
                        month = rq.form['%s_from_month' % prefix]
                        day   = rq.form['%s_from_day' % prefix]
                        fromDate = self._getDateTime(year, month, day, True)
                        # Get the "to" value"
                        year  = rq.form['%s_to_year' % prefix]
                        month = rq.form['%s_to_month' % prefix]
                        day   = rq.form['%s_to_day' % prefix]
                        toDate = self._getDateTime(year, month, day, False)
                        value = (fromDate, toDate)
                    elif type.startswith('string'):
                        # In the case of a string, it could be necessary to
                        # apply some text transform.
                        if len(type) > 6:
                            transform = type.split('-')[1]
                            if (transform != 'none') and value:
                                exec 'value = value.%s()' % \
                                     self.transformMethods[transform]
                if isinstance(value, list):
                    # It is a list of values. Check if we have an operator for
                    # the field, to see if we make an "and" or "or" for all
                    # those values. "or" will be the default.
                    operKey = 'o_%s' % name[2:]
                    oper = ' %s ' % rq.form.get(operKey, 'or').upper()
                    value = oper.join(value)
                criteria[name[2:]] = value
        # Complete criteria with Ref info if the search is restricted to
        # referenced objects of a Ref field.
        refInfo = rq.get('ref', None)
        if refInfo: criteria['_ref'] = refInfo
        rq.SESSION['searchCriteria'] = criteria

    def onSearchObjects(self):
        '''This method is called when the user triggers a search from
           pxSearch.'''
        rq = self.REQUEST
        self.storeSearchCriteria()
        # Go to the screen that displays search results
        backUrl = '%s/query?className=%s&&search=customSearch' % \
                  (self.absolute_url(), rq['className'])
        return self.goto(backUrl)

    def getJavascriptMessages(self):
        '''Returns the translated version of messages that must be shown in
           Javascript popups.'''
        res = ''
        for msg in jsMessages:
            res += 'var %s = "%s";\n' % (msg, self.translate(msg))
        return res

    def getColumnsSpecifiers(self, className, columnLayouts, dir):
        '''Extracts and returns, from a list of p_columnLayouts, info required
           for displaying columns of field values for instances of p_className,
           either in a result screen or for a Ref field.'''
        res = []
        for info in columnLayouts:
            fieldName, width, align = ColumnLayout(info).get()
            align = self.flipLanguageDirection(align, dir)
            field = self.getAppyType(fieldName, className)
            if not field:
                self.log('field "%s", used in a column specifier, was not ' \
                         'found.' % fieldName, type='warning')
            else:
                res.append(Object(field=field, width=width, align=align))
        return res

    def getRefInfo(self, refInfo=None):
        '''When a search is restricted to objects referenced through a Ref
           field, this method returns information about this reference: the
           source class and the Ref field. If p_refInfo is not given, we search
           it among search criteria in the session.'''
        if not refInfo and (self.REQUEST.get('search', None) == 'customSearch'):
            criteria = self.REQUEST.SESSION.get('searchCriteria', None)
            if criteria and criteria.has_key('_ref'): refInfo = criteria['_ref']
        if not refInfo: return None, None
        objectUid, fieldName = refInfo.split(':')
        obj = self.getObject(objectUid)
        return obj, fieldName

    def getGroupedSearches(self, klass):
        '''Returns an object with 2 attributes:
           * "searches" stores the searches that are defined for p_klass;
           * "default" stores the search defined as the default one.
           Every item representing a search is a dict containing info about a
           search or about a group of searches.
        '''
        res = []
        default = None # Also retrieve the default one here
        groups = {} # The already encountered groups
        page = Page('searches') # A dummy page required by class UiGroup
        # Get the searches statically defined on the class
        className = self.getPortalType(klass)
        searches = ClassDescriptor.getSearches(klass, tool=self.appy())
        # Get the dynamically computed searches
        if hasattr(klass, 'getDynamicSearches'):
            searches += klass.getDynamicSearches(self.appy())
        for search in searches:
            # Create the search descriptor
            uiSearch = UiSearch(search, className, self)
            if not search.group:
                # Insert the search at the highest level, not in any group
                res.append(uiSearch)
            else:
                uiGroup = search.group.insertInto(res, groups, page, className,
                                                  content='searches')
                uiGroup.addElement(uiSearch)
            # Is this search the default search?
            if search.default: default = uiSearch
        return Object(searches=res, default=default)

    def getSearch(self, className, name, ui=False):
        '''Gets the Search instance (or a UiSearch instance if p_ui is True)
           corresponding to the search named p_name, on class p_className.'''
        initiator = None
        if name == 'customSearch':
            # It is a custom search whose parameters are in the session
            fields = self.REQUEST.SESSION['searchCriteria']
            res = Search('customSearch', **fields)
        elif (name == 'allSearch') or not name:
            # It is the search for every instance of p_className
            res = Search('allSearch')
            klass = self.getAppyClass(className)
            if hasattr(klass, 'searchAdvanced'):
                # Take into account default params for the advanced search
                res.merge(klass.searchAdvanced)
        elif name == 'fromSearch':
            # It is the search for selecting a template for creating an object
            fromClass = self.REQUEST.get('fromClass')
            means = self.getCreateMeans(self.getAppyClass(fromClass))
            res = getattr(means, 'search', None)
            initiator = UiSearch.TemplateInitiator(fromClass)
        elif ',' in name:
            # The search is defined in a field
            id, name, mode = name.split(',')
            # Get the object with this "id". In the case of a Ref field with
            # link=popup, the initiator object can be a temp object.
            obj = self.getObject(id, appy=True) or \
                  self.getObject(id, appy=True, temp=True)
            field = obj.getField(name)
            if field.type == 'Ref':
                initiator = UiSearch.RefInitiator(obj, field, name, mode)
                res = field.getSelect(obj)
            elif field.type == 'Computed':
                res = field.getSearch(obj)
        else:
            appyClass = self.getAppyClass(className)
            # Search among static searches
            res = ClassDescriptor.getSearch(appyClass, name)
            if not res and hasattr(appyClass, 'getDynamicSearches'):
                # Search among dynamic searches
                for search in appyClass.getDynamicSearches(self.appy()):
                    if search.name == name:
                        res = search
                        break
        # Return a UiSearch if required
        if ui: res = UiSearch(res, className, self, initiator)
        return res

    def getPxTarget(self, zobj, px):
        '''When a p_px is requested from Ajax, this method gets the target PX
           field or search when relevant.'''
        res = Object(className=None, name=None, pxName=None, field=None)
        if len(px) == 3:
            res.className, res.name, res.pxName = px
        elif len(px) == 2:
            res.name, res.pxName = px
        else:
            # Only the PX name: the PX is not field or search-related
            res.pxName = px
            return res
        # Find the field or search named "res.name" and put it in "res.field"
        if not res.className:
            # If no class name is specified, it can only be a field
            res.field = zobj.getAppyType(res.name)
        else:
            # Else, it can be a field or a search
            res.field = zobj.getAppyType(res.name, res.className) or \
                        self.getSearch(res.className, res.name, ui=True)
        return res

    def getLiveSearch(self, klass, keywords):
        '''Gets the Search instance for performing a live search on p_klass'''
        if not keywords.endswith('*'): keywords += '*'
        res = Search('liveSearch', SearchableText=keywords)
        if hasattr(klass, 'searchAdvanced'):
            # Take into account default params for the advanced search
            res.merge(klass.searchAdvanced)
        return res

    def advancedSearchEnabledFor(self, klass):
        '''Is advanced search visible for p_klass ?'''
        # By default, advanced search is enabled
        if not hasattr(klass, 'searchAdvanced'): return True
        # Evaluate attribute "show" on this Search instance representing the
        # advanced search.
        return klass.searchAdvanced.isShowable(klass, self.appy())

    def portletBottom(self, klass):
        '''Is there a custom zone to display at the bottom of the portlet zone
           for p_klass?'''
        if not hasattr(klass, 'getPortletBottom'): return ''
        res = klass.getPortletBottom(self.appy())
        if not res: return ''
        return res

    def getNavigationInfo(self, nav, inPopup):
        '''Produces a Siblings instance from navigation info p_nav.'''
        return Siblings.get(nav, self, inPopup)

    def getGroupedSearchFields(self, searchInfo):
        '''This method transforms p_searchInfo.fields, which is a "flat"
           list of fields, into a list of lists, where every sub-list having
           length p_searchInfo.nbOfColumns. For every field, scolspan
           (=colspan "for search") is taken into account.'''
        res = []
        row = []
        rowLength = 0
        for field in searchInfo.fields:
            # Can I insert this field in the current row?
            remaining = searchInfo.nbOfColumns - rowLength
            if field.scolspan <= remaining:
                # Yes.
                row.append(field)
                rowLength += field.scolspan
            else:
                # We must put the field on a new line. Complete the current one
                # if not complete.
                while rowLength < searchInfo.nbOfColumns:
                    row.append(None)
                    rowLength += 1
                res.append(row)
                row = [field]
                rowLength = field.scolspan
        # Complete the last unfinished line if required.
        if row:
            while rowLength < searchInfo.nbOfColumns:
                row.append(None)
                rowLength += 1
            res.append(row)
        return res

    # --------------------------------------------------------------------------
    # Authentication-related methods
    # --------------------------------------------------------------------------
    def identifyUser(self, alsoSpecial=False):
        '''To identify a user means: get its login, password and authentication
           context. There are several places to look for this information: http
           authentication, cookie of credentials coming from the web form.

           If no user could be identified, and p_alsoSpecial is True, we will
           nevertheless identify a "special user": "system", representing the
           system itself (running at startup or in batch mode) or "anon",
           representing an anonymous user.'''
        tool = self.appy()
        req = tool.request
        login = password = ctx = place = None
        # a. Identify the user from HTTP basic authentication
        if getattr(req, '_auth', None):
            # Credentials are present (used by a peer application, or the ZMI).
            # Decode it.
            creds = req._auth
            if creds.lower().startswith('basic '):
                try:
                    creds = creds.split(' ')[-1]
                    login, password = base64.decodestring(creds).split(':', 1)
                    if login: place = 'basic'
                except Exception, e:
                    pass
        # b. Identify the user from the authentication cookie
        if not login:
            try:
                login, password, ctx = gutils.readCookie(req)
            except Exception, e:
                self.log('Unreadable cookie (%s)' % str(e), type='error')
            if login: place = 'cookie'
        # c. Identify the user from the authentication form
        if not login:
            login = req.get('__ac_name')
            if login: login = login.strip()
            password = req.get('__ac_password', '')
            ctx = req.get('__ac_ctx')
            if login: place = 'form'
        # d. Identify the user from a SSO reverse proxy
        if not login:
            sso = self.getProductConfig(True).sso
            if sso:
                login = sso.extractUserLogin(tool, req, warn=not alsoSpecial)
                if login: place = 'sso'
        # Stop identification here if we don't need to return a special user
        if not alsoSpecial: return login, password, ctx, place
        # d. All the identification methods failed. So identify the user as
        # "anon" or "system".
        if not login:
            # If we have a fake request, we are at startup or in batch mode and
            # the user is "system". Else, it is "anon". At Zope startup, Appy
            # uses an Object instance as a fake request. In "zopectl run" mode
            # (the Zope batch mode), Appy adds a param "_fake_" on the request
            # object created by Zope.
            if (req.__class__.__name__ == 'Object') or \
               (hasattr(req, '_fake_') and req._fake_):
                login = 'system'
            else:
                login = 'anon'
        return login, password, ctx, place

    def getUser(self, authenticate=False, source='any'):
        '''Gets the current user. If p_authenticate is True, in addition to
           finding the logged user and returning it (=identification), we check
           if found credentials are valid (=authentication).

           If p_authenticate is True and p_source is:
           * "zodb", authentication is performed locally;
           * "ldap", authentication is performed on a LDAP (if a LDAP
                     configuration is found);
           * "sso",  authentication is performed based on HTTP headers from the
                     request, set by some SSO reverse proxy;
           * "any",  authentication is performed on the local User object, be it
                     really local or a copy of an external (ldap or sso) user.
        '''
        tool = self.appy()
        req = tool.request
        # Try first to return the user that can be cached on the request. In
        # this case, we suppose authentication has previously been done, and we
        # just return the cached user.
        if hasattr(req, 'user'): return req.user
        # Identify the user (=find its login, password and authentication
        # context). If we don't need to authenticate the user, we ask to
        # identify a user or, if impossible, a special user.
        login,password,ctx,place=self.identifyUser(alsoSpecial=not authenticate)
        # Stop here if no user was found and authentication was required
        if authenticate and not login: return
        # Now, get the User instance. If the user was identified from HTTP
        # headers (SSO), always get it via the SsoConfig.
        cfg = self.getProductConfig(True)
        if place == 'sso': source = 'sso'
        if source == 'zodb':
            # Get the User object, but only if it is a true local user
            user = tool.search1('User', noSecurity=True, login=login)
            if user and (user.source != 'zodb'): user = None # Not a local one
        elif source in ('ldap', 'sso'):
            user = None
            extSource = getattr(cfg, source)
            if extSource:
                if source == 'ldap':
                    user = extSource.getUser(tool, login, password)
                else:
                    user = extSource.getUser(tool, login,
                                             createIfNotFound=authenticate)
        elif source == 'any':
            # Get the User object, be it really local or representing an
            # external user. This way, we avoid contacting the distant source
            # every time authentication is required.
            user = tool.search1('User', noSecurity=True, login=login)
        if not user: return
        login = user.login # May have been transformed by a source
        # Authenticate the user if required. In the case of SSO, authentication
        # has already been performed by the reverse proxy.
        if authenticate and (place != 'sso'):
            if (user.state == 'inactive') or \
               (not user.checkPassword(password)) or \
               (cfg.authContext and \
                cfg.authContext.isMandatory(tool) and not ctx):
                # Disable the authentication cookie and remove credentials
                # stored on the request.
                req.RESPONSE.expireCookie('_appy_', path='/')
                k = 'HTTP_AUTHORIZATION'
                req._auth = req[k] = req._orig_env[k] = None
                return
            # Create an authentication cookie for this user
            gutils.writeCookie(login, password, ctx, req)
        # Cache the user and some precomputed values, for performance
        req.user = user
        req.userLogin = login
        req.authContext = ctx
        if ctx: req.authContextName = cfg.authContext.getName(tool, ctx)
        req.userRoles = user.getRoles()
        req.userLogins = user.getLogins()
        req.zopeUser = user.getZopeUser()
        return user

    def performLogin(self):
        '''Logs the user in'''
        rq = self.REQUEST
        jsEnabled = rq.get('js_enabled', False) in ('1', 1)
        cookiesEnabled = rq.get('cookies_enabled', False) in ('1', 1)
        if jsEnabled and not cookiesEnabled:
            msg = self.translate('enable_cookies')
            return self.goto(self.getReferer(), msg)
        # Authenticate the user
        if self.getUser(authenticate=True, source='zodb') or \
           self.getUser(authenticate=True, source='ldap'):
            msg = self.translate('login_ok')
            logMsg = 'logged in.'
            success = True
        else:
            msg = self.translate('login_ko')
            login = rq.get('__ac_name') or '<empty>'
            logMsg = 'authentication failed with login %s.' % login
            success = False
        self.log(logMsg)
        # Must the user be redirected to some URL ?
        gotoUrl = rq.get('goto', None)
        siteUrl = self.getSiteUrl()
        if not success:
            backUrl = siteUrl
            if gotoUrl: backUrl += '?goto=%s' % urllib.quote(gotoUrl)
        else:
            if gotoUrl:
                backUrl = '%s/%s' % (siteUrl, gotoUrl)
                msg = None # No need to get the welcome message here
            else:
                backUrl = siteUrl
        return self.goto(backUrl, msg)

    def performLogout(self):
        '''Logs out the current user when he clicks on "disconnect"'''
        rq = self.REQUEST
        userId = self.getUser().login
        # Perform the logout in acl_users
        rq.RESPONSE.expireCookie('_appy_', path='/')
        # Invalidate the user session
        try:
            sdm = self.session_data_manager
        except AttributeError, ae:
            # When ran in test mode, session_data_manager is not there
            sdm = None
        if sdm:
            session = sdm.getSessionData(create=0)
            if session is not None:
                session.invalidate()
        self.log('logged out.')
        # Remove user from variable "loggedUsers"
        if self.loggedUsers.has_key(userId): del self.loggedUsers[userId]
        return self.goto(self.getApp().absolute_url())

    def getLogoutUrl(self):
        '''The "logout" URL may not be the standard Appy one if the app is
           behind a SSO reverse proxy.'''
        if self.getUser().source == 'sso':
            return self.getProductConfig(True).sso.logoutUrl
        return '%s/performLogout' % self.absolute_url()

    # This dict stores, for every logged user, the date/time of its last access
    loggedUsers = {}
    staticExtensions = ('.jpg', '.jpeg', '.gif', '.png', '.js', '.css', '.htm',
                        '.html')
    def rememberAccess(self, user):
        '''Every time there is a hit on the server, this method is called in
           order to update global dict loggedUsers (see above).'''
        self.loggedUsers[user.login] = time.time()
        # "Touch" the SESSION object. Else, expiration won't occur.
        session = self.REQUEST.SESSION

    def validate(self, request, auth='', roles=_noroles):
        '''This method performs authentication and authorization. It is used as
           a replacement for Zope's AccessControl.User.BasicUserFolder.validate,
           that allows to manage cookie-based authentication.'''
        v = request['PUBLISHED'] # The published object
        tool = self.getParentNode().config
        # v is the object (value) we're validating access to
        # n is the name used to access the object
        # a is the object the object was accessed through
        # c is the physical container of the object
        a, c, n, v = self._getobcontext(v, request)
        # Authorize anyone to static content (image, js, css...)
        id = a.getId()
        if id and (os.path.splitext(id)[-1].lower() in tool.staticExtensions):
            return self._nobody.__of__(self)
        # Skip authorization when the performing http login: else, it will be
        # done twice.
        if (id == 'config') and (v.__name__ == 'performLogin'):
            return self._nobody.__of__(self)
        # Identify and authenticate the user
        user = tool.getUser(authenticate=True, source='any')
        if not user:
            # Login and/or password incorrect. Try to authorize and return the
            # anonymous user.
            if self.authorize(self._nobody, a, c, n, v, roles):
                return self._nobody.__of__(self)
            else:
                return
        else:
            # We found a user and his password was correct. Try to authorize him
            # against the published object. By the way, remember its last access
            # to this system.
            tool.rememberAccess(user)
            user = user.getZopeUser()
            if self.authorize(user, a, c, n, v, roles):
                return user.__of__(self)
            # That didn't work. Try to authorize the anonymous user.
            elif self.authorize(self._nobody, a, c, n, v, roles):
                return self._nobody.__of__(self)
            else:
                return

    # Patch BasicUserFolder with our version of m_validate above.
    from AccessControl.User import BasicUserFolder
    BasicUserFolder.validate = validate

    def getUserName(self, login=None, normalized=False):
        '''Gets the user name corresponding to p_login (or the currently logged
           user if None), or the p_login itself if the user does not exist
           anymore. If p_normalized is True, special chars in the first and last
           names are normalized.'''
        tool = self.appy()
        if not login:
            user = tool.user
        else:
            user = tool.search1('User', noSecurity=True, login=login)
            if not user: return login
        return user.getTitle(normalized=normalized)

    def tempFile(self):
        '''A temp file has been created in a temp folder. This method returns
           this file to the browser.'''
        rq = self.REQUEST
        baseFolder = os.path.join(sutils.getOsTempFolder(), self.getAppName())
        baseFolder = os.path.join(baseFolder, rq.SESSION.id)
        fileName   = os.path.join(baseFolder, rq.get('name', ''))
        if os.path.exists(fileName):
            f = file(fileName)
            content = f.read()
            f.close()
            # Remove the temp file
            os.remove(fileName)
            return content
        return 'File does not exist'

    def getResultPodFields(self, contentType):
        '''Finds, among fields defined on p_contentType, which ones are Pod
           fields that need to be shown on a page displaying query results.'''
        # Skip this if we are searching multiple content types
        if ',' in contentType: return ()
        return [f for f in self.getAllAppyTypes(contentType) \
                if (f.type == 'Pod') and (f.show == 'query')]

    def formatDate(self, date, format=None, withHour=True, language=None):
        '''Returns p_date formatted as specified by p_format, or tool.dateFormat
           if not specified. If p_withHour is True, hour is appended, with a
           format specified in tool.hourFormat.'''
        tool = self.appy()
        fmt = format or tool.dateFormat
        # Resolve appy-specific formatting symbols used for getting translated
        # names of days or months:
        # - %dt: translated name of day
        # - %DT: translated name of day, capitalized
        # - %mt: translated name of month
        # - %MT: translated name of month, capitalized
        if ('%dt' in fmt) or ('%DT' in fmt):
            day = self.translate('day_%s' % date._aday, language=language)
            fmt = fmt.replace('%dt', day.lower()).replace('%DT', day)
        if ('%mt' in fmt) or ('%MT' in fmt):
            month = self.translate('month_%s' % date._amon, language=language)
            fmt = fmt.replace('%mt', month.lower()).replace('%MT', month)
        # Resolve all other, standard, symbols
        res = date.strftime(fmt)
        # Append hour from tool.hourFormat
        if withHour and (date._hour or date._minute):
            res += ' (%s)' % date.strftime(tool.hourFormat)
        return res

    def generateUid(self, className):
        '''Generates a UID for an instance of p_className.'''
        name = className.split('_')[-1]
        randomNumber = str(random.random()).split('.')[1].replace('e-', '')
        timestamp = ('%f' % time.time()).replace('.', '')
        return '%s%s%s' % (name, timestamp, randomNumber)

    def getMainPages(self):
        '''Returns the main pages.'''
        if hasattr(self.o.aq_base, 'pages') and self.o.pages:
            return [self.getObject(uid) for uid in self.o.pages ]
        return ()

    def askPasswordReinit(self):
        '''A user (anonymmous) does not remember its password. Here we will
           send him a mail containing a link that will trigger password
           re-initialisation.'''
        login = self.REQUEST.get('login').strip()
        appyTool = self.appy()
        user = appyTool.search1('User', login=login, noSecurity=True)
        msg = self.translate('reinit_mail_sent')
        backUrl = self.getReferer()
        if not user:
            # Return the message nevertheless. This way, malicious users can't
            # deduce information about existing users.
            return self.goto(backUrl, msg)
        # If login is an email, use it. Else, use user.email instead.
        email = user.login
        if not String.EMAIL.match(email):
            email = user.email
        if not email:
            # Impossible to re-initialise the password.
            return self.goto(backUrl, msg)
        # Create a temporary file whose name is the user login and whose
        # content is a generated token.
        f = file(os.path.join(sutils.getOsTempFolder(), login), 'w')
        token = String().generatePassword()
        f.write(token)
        f.close()
        # Send an email
        initUrl = '%s/doPasswordReinit?login=%s&token=%s' % \
                  (self.absolute_url(), login, token)
        subject = self.translate('reinit_password')
        map = {'url':initUrl, 'siteUrl':self.getSiteUrl()}
        body= self.translate('reinit_password_body', mapping=map, format='text')
        appyTool.sendMail(email, subject, body)
        return self.goto(backUrl, msg)

    def doPasswordReinit(self):
        '''Performs the password re-initialisation.'''
        rq = self.REQUEST
        login = rq['login']
        token = rq['token']
        # Check if such token exists in temp folder
        res = None
        siteUrl = self.getSiteUrl()
        tokenFile = os.path.join(sutils.getOsTempFolder(), login)
        if os.path.exists(tokenFile):
            f = file(tokenFile)
            storedToken = f.read()
            f.close()
            if storedToken == token:
                # Generate a new password for this user
                appyTool = self.appy()
                user = appyTool.search1('User', login=login, noSecurity=True)
                newPassword = user.setPassword()
                # Send the new password by email
                email = login
                if not String.EMAIL.match(email):
                    email = user.email
                subject = self.translate('new_password')
                map = {'password': newPassword, 'siteUrl': siteUrl}
                body = self.translate('new_password_body', mapping=map,
                                      format='text')
                appyTool.sendMail(email, subject, body)
                os.remove(tokenFile)
                res = self.goto(siteUrl, self.translate('new_password_sent'))
        if not res:
            res = self.goto(siteUrl, self.translate('wrong_password_reinit'))
        return res

    def getGoogleAnalyticsCode(self):
        '''If the config defined a Google Analytics ID, this method returns the
           Javascript code to be included in every page, allowing Google
           Analytics to work.'''
        # Disable Google Analytics when we are in debug mode.
        if self.isDebug(): return
        # Disable Google Analytics if no ID is found in the config.
        gaId = self.getProductConfig(True).googleAnalyticsId
        if not gaId: return
        # Google Analytics must be enabled: return the chunk of Javascript
        # code specified by Google.
        code = "var _gaq = _gaq || [];\n" \
               "_gaq.push(['_setAccount', '%s']);\n" \
               "_gaq.push(['_trackPageview']);\n" \
               "(function() {\n" \
               "  var ga = document.createElement('script'); " \
               "ga.type = 'text/javascript'; ga.async = true;\n" \
               "  ga.src = ('https:' == document.location.protocol ? " \
               "'https://ssl' : 'http://www') + " \
               "'.google-analytics.com/ga.js';\n" \
               "  var s = document.getElementsByTagName('script')[0]; " \
               "s.parentNode.insertBefore(ga, s);\n" \
               "})();\n" % gaId
        return code

    def getButtonCss(self, label, small=True):
        '''Gets the CSS class(es) to set on a button, given it l_label and its
           size (p_small or not).'''
        # CSS for a small button. No minimum width applies: small button are
        # meant to be small.
        if small: return 'buttonSmall button'
        # CSS for a normal button. A minimum width (via buttonFixed) is defined
        # when the label is small: it produces ranges of buttons of the same
        # width (excepted when labels are too large), which is more beautiful.
        if len(label) < 15: return 'buttonFixed button'
        return 'button'

    def getLinksTargetInfo(self, klass, back=None):
        '''Appy allows to open links to view or edit instances of p_klass
           either via the same browser window, or via a popup. This method
           returns info about that, as an object having 2 attributes:
           - target is "_self" if the link leads to the same browser window,
                    "appyIFrame" if the link must be opened in a popup;
           - openPopup  is unused if target is "_self" or contains the
                        Javascript code to open the popup.'''
        res = Object(target='_self', openPopup='')
        if hasattr(klass, 'popup'):
            res.target = 'appyIFrame'
            d = klass.popup
            if isinstance(d, basestring):
                # Width only
                params = d[:-2]
            else:
                # Width and height
                params = "%s, %s" % (d[0][:-2], d[1][:-2])
            # If "back" is specified, it corresponds to some tag on the main
            # page, that must be ajax-refreshed when coming back from the popup.
            # Else, when back, the entire page will be reloaded.
            if back: params += ", '%s'" % back
            res.openPopup = "openPopup('iframePopup',null,%s)" % params
        return res

    def backFromPopup(self):
        '''Returns the PX allowing to close the iframe popup and refresh the
           base page.'''
        return self.appy().pxBack({'ztool': self})

    ieRex = re.compile('MSIE\s+(\d\.\d)')
    ieMin = '9' # We do not support IE below this version
    def getBrowserIncompatibility(self):
        '''Produces an error message if the browser in use is not compatible
           with Appy.'''
        res = self.ieRex.search(self.REQUEST.get('HTTP_USER_AGENT'))
        if not res: return
        version = res.group(1)
        if version < self.ieMin:
            mapping = {'version': version, 'min': self.ieMin}
            return self.translate('wrong_browser', mapping=mapping)

    def executeAjaxAction(self, action, obj, field):
        '''When PX "pxAjax" is called to get some chunk of XHTML via an Ajax
           request, a server action can be executed before rendering the XHTML
           chunk. This method executes this action.'''
        if action.startswith(':'):
            # The action corresponds to a method on Appy p_obj
            msg = getattr(obj, action[1:])()
        else:
            # The action must be executed on p_field if present, on obj.o else.
            if field: msg = getattr(field, action)(obj.o)
            else: msg = getattr(obj.o, action)()
        return msg

    def updatePxContextFromRequest(self):
        '''Takes any user-defined key from the request and put it as a variable
           on the current PX context.'''
        req = self.REQUEST
        ctx = req.pxContext
        # Get "form" data (get, post) and cookie values
        for source in (req.form, req.cookies):
            for k, v in source.iteritems():
                # Convert v to some Python data when relevant
                if v in ('True', 'False', 'true', 'false'):
                    exec 'v = %s' % v.capitalize()
                elif v.isdigit(): v = int(v)
                ctx[k] = v

    def patchRequestFromTemplate(self, obj, req):
        '''p_obj is a temp object that is going to be edited via pxEdit. If a
           template obj must be used to pre-fill the web form, patch the request
           with the values retrieved on this template object.'''
        if not obj.isTemporary(): return
        templateId = req.get('template')
        if not templateId: return
        template = self.getObject(templateId)
        for field in template.getAllAppyTypes():
            value = field.getCopyValue(template)
            if value != None: req[field.name] = value

    def check(self):
        '''Returns monitoring info about the running application'''
        cfg = self.getProductConfig(True)
        return cfg.monitoring.get(self.REQUEST, cfg)
# ------------------------------------------------------------------------------
