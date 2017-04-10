'''This package contains stuff used at run-time for installing a generated
   Zope product.'''

# ------------------------------------------------------------------------------
import os, os.path, sys
import appy
import appy.version
import appy.gen as gen
from appy.gen.po import PoParser
from appy.gen.indexer import defaultIndexes, updateIndexes
from appy.gen.migrator import Migrator
from appy.gen import utils as gutils
from appy.shared.data import languages
from appy.shared.utils import getTempFileName

# ------------------------------------------------------------------------------
homePage = '<tal:h define="dummy python: request.RESPONSE.redirect(' \
           'context.config.getHomePage())"/>'
errorPage = '<tal:h define="dummy python: request.RESPONSE.write(' \
            'request.traverse(\'/\').config.getErrorPage(options))"/>'

# Zope hacks -------------------------------------------------------------------
class FakeXmlrpc:
    '''Fake class that behaves like Zope's xmlrpc module. This cheat disables
       Zope's XMLRPC.'''
    def parse_input(self, value): return None, ()
    def response(self, response): return response

class FakeZCatalog:
    # This prevents Zope frop crashing when, while updating the catalog, an
    # entry in the catalog corresponds to a missing object.
    def resolve_url(self, path, REQUEST):
        '''Cheat: "hasattr" test has been added in first line'''
        if REQUEST and hasattr(REQUEST, 'script'):
            script=REQUEST.script
            if path.find(script) != 0:
                path='%s/%s' % (script, path)
            try: return REQUEST.resolve_url(path)
            except: pass
    try:
        from Products.ZCatalog.ZCatalog import ZCatalog
        ZCatalog.resolve_url = resolve_url
    except ImportError:
        pass

class FakeSiteErrorLog:
    # Prevent Zope from logging Unauthorized errors wrapped into EvaluationError
    # instances.
    def raising(self, info):
        if info[0].__name__ == 'EvaluationError':
            orig = getattr(info[1], 'originalError', None)
            if orig.__class__.__name__ == 'Unauthorized': return
        from Products.SiteErrorLog.SiteErrorLog import SiteErrorLog
        return appy.Hack.base(SiteErrorLog.raising)
    try:
        from Products.SiteErrorLog.SiteErrorLog import SiteErrorLog
        appy.Hack.patch(SiteErrorLog.raising, raising)
    except ImportError:
        pass

def onDelSession(sessionObject, container):
    '''This function is called when a session expires.'''
    rq = container.REQUEST
    if rq.cookies.has_key('_appy_') and rq.cookies.has_key('_ZopeId') and \
       (rq['_ZopeId'] == sessionObject.token):
        # The request comes from a guy whose session has expired.
        resp = rq.RESPONSE
        resp.expireCookie('_appy_', path='/')
        resp.setHeader('Content-Type', 'text/html')
        resp.write('<center>For security reasons, your session has ' \
                   'expired.</center>')

# ------------------------------------------------------------------------------
class ZopeInstaller:
    '''This Zope installer runs every time Zope starts and encounters this
       generated Zope product.'''
    # Info about the default users that are always present.
    defaultUsers = {'admin': ('Manager',), 'system': ('Manager',), 'anon': ()}
    favIcon = 'favicon.ico'

    def __init__(self, zopeContext, config, classes):
        self.zopeContext = zopeContext
        self.app = zopeContext._ProductContext__app # The root of the Zope tree
        self.config = config
        self.classes = classes
        # Unwrap some useful config variables
        self.productName = config.PROJECTNAME
        self.languages = config.appConfig.languages
        self.logger = config.logger

    def patchCssFile(self, f):
        '''p_f is an open file handler containing CSS content. We will create a
           temporary file, resolve Appy variables in it and return it.'''
        # Read the CSS content
        css = f.read()
        f.close()
        # Resolve Appy variables in it
        ui = self.config.appConfig.ui
        for name, value in ui.__dict__.iteritems():
            # Ignore non string attributes
            if name.startswith('_') or not isinstance(value, basestring):
                continue
            css = css.replace('|%s|' % name, value)
        # Dump the result in a temp file and return it
        fileName = getTempFileName(prefix='appycss', extension='css')
        f = file(fileName, 'w')
        f.write(css)
        f.close()
        f = file(fileName)
        return f

    def installUi(self):
        '''Installs the user interface'''
        # Some useful imports
        from OFS.Folder import manage_addFolder
        from OFS.Image import manage_addImage, manage_addFile
        # Delete the existing folder if it existed
        zopeContent = self.app.objectIds()
        for name in ('ui', self.favIcon):
            if name in zopeContent: self.app.manage_delObjects([name])
        manage_addFolder(self.app, 'ui')
        # Browse the physical ui folders (the Appy one and an app-specific, if
        # the app defines one) and create the corresponding objects in the Zope
        # folder. In the case of files having the same name in both folders,
        # the one from the app-specific folder is chosen.
        j = os.path.join
        uiFolders = [j(j(appy.getPath(), 'gen'), 'ui')]
        for uiFolder in self.config.appConfig.uiFolders:
            if uiFolder.startswith('..'):
                folder = j(os.path.dirname(self.config.diskFolder),uiFolder[3:])
            else:
                folder = j(self.config.diskFolder, uiFolder)
            if os.path.exists(folder):
                uiFolders.insert(0, folder)
        for ui in uiFolders:
            for root, dirs, files in os.walk(ui):
                folderName = root[len(ui):]
                # Get the Zope folder that corresponds to this name
                zopeFolder = self.app.ui
                if folderName:
                    for name in folderName.strip(os.sep).split(os.sep):
                        zopeFolder = zopeFolder._getOb(name)
                # Create sub-folders at this level
                for name in dirs:
                    if not hasattr(zopeFolder.aq_base, name):
                        manage_addFolder(zopeFolder, name)
                # Create files at this level
                for name in files:
                    ext = os.path.splitext(name)[1]
                    if hasattr(zopeFolder.aq_base, name): continue
                    f = file(j(root, name))
                    if name == self.favIcon:
                        if not hasattr(self.app, name):
                            # Copy it at the root. Else, IE won't notice it.
                            manage_addImage(self.app, name, f)
                    elif ext in gen.File.imageExts:
                        manage_addImage(zopeFolder, name, f)
                    elif (ext == '.css') and root.endswith('/ui'):
                        # Avoid patching CSS files from third-party products
                        manage_addFile(zopeFolder, name, self.patchCssFile(f))
                    else:
                        manage_addFile(zopeFolder, name, f)
                    f.close()
        # Update home and error pages
        from Products.PageTemplates.ZopePageTemplate import \
             manage_addPageTemplate
        if 'index_html' in zopeContent:
            self.app.manage_delObjects(['index_html'])
        manage_addPageTemplate(self.app, 'index_html', '', homePage)
        if 'standard_error_message' in zopeContent:
            self.app.manage_delObjects(['standard_error_message'])
        manage_addPageTemplate(self.app, 'standard_error_message', '',
                               errorPage)

    def installCatalog(self):
        '''Create the catalog at the root of Zope if id does not exist.'''
        if 'catalog' not in self.app.objectIds():
            # Create the catalog
            from Products.ZCatalog.ZCatalog import manage_addZCatalog
            manage_addZCatalog(self.app, 'catalog', '')
            self.logger.info('Appy catalog created.')

        # Create lexicons for ZCTextIndexes
        catalog = self.app.catalog
        lexicons = catalog.objectIds()
        from Products.ZCTextIndex.ZCTextIndex import manage_addLexicon
        if 'xhtml_lexicon' not in lexicons:
            lex = appy.Object(group='XHTML indexer', name='XHTML indexer')
            manage_addLexicon(catalog, 'xhtml_lexicon', elements=[lex])
        if 'text_lexicon' not in lexicons:
            lex = appy.Object(group='Text indexer', name='Text indexer')
            manage_addLexicon(catalog, 'text_lexicon', elements=[lex])
        if 'list_lexicon' not in lexicons:
            lex = appy.Object(group='List indexer', name='List indexer')
            manage_addLexicon(catalog, 'list_lexicon', elements=[lex])

        # Delete the deprecated one if it exists
        if 'lexicon' in lexicons: catalog.manage_delObjects(['lexicon'])

        # Create or update Appy-wide indexes and field-related indexes
        indexInfo = defaultIndexes.copy()
        tool = self.app.config
        for className in self.config.attributes.iterkeys():
            wrapperClass = tool.getAppyClass(className, wrapper=True)
            indexInfo.update(wrapperClass.getIndexes(includeDefaults=False))
        updateIndexes(self, indexInfo)
        # Re-index index "SearchableText", wrongly defined for Appy < 0.8.3
        stIndex = catalog.Indexes['SearchableText']
        if stIndex.indexSize() == 0:
            self.logger.info('reindexing SearchableText...')
            catalog.reindexIndex('SearchableText', self.app.REQUEST)
            self.logger.info('done.')

    def installBaseObjects(self):
        '''Creates the tool and the base data folder if they do not exist.'''
        # Create the tool.
        zopeContent = self.app.objectIds()
        from OFS.Folder import manage_addFolder

        if 'config' not in zopeContent:
            toolName = '%sTool' % self.productName
            gutils.createObject(self.app, 'config', toolName, self.productName,
                                wf=False, noSecurity=True)
        # Create the base data folder
        if 'data' not in zopeContent: manage_addFolder(self.app, 'data')

        # Remove some default objects created by Zope but not useful to Appy
        for name in ('standard_html_footer', 'standard_html_header',\
                     'standard_template.pt'):
            if name in zopeContent: self.app.manage_delObjects([name])

    def installTool(self):
        '''Updates the tool (now that the catalog is created) and updates its
           inner objects (users, groups, translations, documents).'''
        tool = self.app.config
        tool.createOrUpdate(True, None)
        appyTool = tool.appy()
        appyTool.log('Appy version is "%s".' % appy.version.short)

        # Execute custom pre-installation code if any
        if hasattr(appyTool, 'beforeInstall'): appyTool.beforeInstall()

        # Create the default users if they do not exist
        for login, roles in self.defaultUsers.iteritems():
            if not appyTool.count('User', noSecurity=True, login=login):
                appyTool.create('users', noSecurity=True, id=login, login=login,
                                password3=login, password4=login, roles=roles)
                appyTool.log('User "%s" created.' % login)
        # Ensure users "anon" and "system" have no email
        for login in ('anon', 'system'):
            user = appyTool.search1('User', noSecurity=True, login=login)
            user.email = None
        # Create group "admins" if it does not exist
        if not appyTool.count('Group', noSecurity=True, login='admins'):
            appyTool.create('groups', noSecurity=True, login='admins',
                            title='Administrators', roles=['Manager'])
            appyTool.log('Group "admins" created.')

        # Create a group for every global role defined in the application
        # (if required).
        if self.config.appConfig.groupsForGlobalRoles:
            for role in self.config.applicationGlobalRoles:
                groupId = role.lower()
                if appyTool.count('Group', noSecurity=True, login=groupId):
                    continue
                appyTool.create('groups', noSecurity=True, login=groupId,
                                title=role, roles=[role])
                appyTool.log('Group "%s", related to global role "%s", was ' \
                             'created.' % (groupId, role))

        # Create or update Translation objects
        translations = [t.o.id for t in appyTool.translations]
        # We browse the languages supported by this application and check
        # whether we need to create the corresponding Translation objects.
        done = []
        for language in self.languages:
            if language in translations: continue
            # We will create, in the tool, the translation object for this
            # language. Determine first its title.
            langId, langEn, langNat = languages.get(language)
            if langEn != langNat:
                title = '%s (%s)' % (langEn, langNat)
            else:
                title = langEn
            appyTool.create('translations', noSecurity=True,
                            id=language, title=title)
            done.append(language)
        if done: appyTool.log('Translations created for %s.' % ', '.join(done))

        # Synchronizes, if required, every Translation object with the
        # corresponding "po" file on disk.
        if appyTool.loadTranslationsAtStartup:
            appFolder = self.config.diskFolder
            appName = self.config.PROJECTNAME
            i18nFolder = os.path.join(appFolder, 'tr')
            done = []
            for translation in appyTool.translations:
                # Get the "po" file
                poName = '%s-%s.po' % (appName, translation.id)
                poFile = PoParser(os.path.join(i18nFolder, poName)).parse()
                for message in poFile.messages:
                    setattr(translation, message.id, message.getMessage())
                done.append(translation.id)
            appyTool.log('translation(s) %s updated (%s messages).' % \
                         (', '.join(done), len(poFile.messages)))

        # Execute custom installation code if any.
        if hasattr(appyTool, 'onInstall'): appyTool.onInstall()

    def configureSessions(self):
        '''Configure the session machinery'''
        # Register a function warning us when a session object is deleted. When
        # launching Zope in test mode, the temp folder does not exist.
        if not hasattr(self.app, 'temp_folder'): return
        sessionData = self.app.temp_folder.session_data
        if self.config.appConfig.enableSessionTimeout:
            sessionData.setDelNotificationTarget(onDelSession)
        else:
            sessionData.setDelNotificationTarget(None)

    def installZopeClasses(self):
        '''Zope-level class registration'''
        for klass in self.classes:
            name = klass.__name__
            module = klass.__module__
            wrapper = klass.wrapperClass
            exec 'from %s import manage_add%s as ctor' % (module, name)
            self.zopeContext.registerClass(meta_type=name,
                constructors = (ctor,), permission = None)
            # Create workflow prototypical instances in __instance__ attributes
            wf = wrapper.getWorkflow()
            if not hasattr(wf, '__instance__'): wf.__instance__ = wf()

    def installAppyTypes(self):
        '''We complete here the initialisation process of every Appy type of
           every gen-class of the application.'''
        appName = self.productName
        for klass in self.classes:
            # Store on wrapper class the ordered list of Appy types
            wrapperClass = klass.wrapperClass
            if not hasattr(wrapperClass, 'title'):
                # Special field "type" is mandatory for every class.
                title = gen.String(multiplicity=(1,1), show='edit',
                                   indexed=True, searchable=True)
                title.init('title', None, 'appy')
                setattr(wrapperClass, 'title', title)
            # Special field "state" must be added for every class. It must be a
            # "select" field, because it will be necessary for displaying the
            # translated state name.
            state = gen.String(validator=gen.Selection('listStates'),
                           show='result', persist=False, indexed=True, height=5)
            state.init('state', None, 'workflow')
            setattr(wrapperClass, 'state', state)
            # Special field "SearchableText" must be added fot every class and
            # will allow to display a search widget for entering keywords for
            # searhing in index "SearchableText".
            searchable = gen.String(show=False, persist=False, indexed=True)
            searchable.init('SearchableText', None, 'appy')
            setattr(wrapperClass, 'SearchableText', searchable)
            # Set field "__fields__" on the wrapper class
            names = self.config.attributes[wrapperClass.__name__[:-8]]
            wrapperClass.__fields__ = [getattr(wrapperClass, n) for n in names]
            # Post-initialise every Appy type
            for baseClass in klass.wrapperClass.__bases__:
                if baseClass.__name__ == 'AbstractWrapper': continue
                for name, appyType in baseClass.__dict__.iteritems():
                    if not isinstance(appyType, gen.Field) or \
                           (isinstance(appyType, gen.Ref) and appyType.isBack):
                        continue # Back refs are initialised within fw refs
                    appyType.init(name, baseClass, appName)

    def installRoles(self):
        '''Installs the application-specific roles if not already done.'''
        roles = list(self.app.__ac_roles__)
        for role in self.config.applicationRoles:
            if role not in roles: roles.append(role)
        self.app.__ac_roles__ = tuple(roles)

    def patchZope(self):
        '''Patches some parts of Zope'''
        # Disable XMLRPC. This way, Zope can transmit HTTP POSTs containing
        # XML to Appy without trying to recognize it himself as XMLRPC requests.
        import ZPublisher.HTTPRequest
        ZPublisher.HTTPRequest.xmlrpc = FakeXmlrpc()

    def installDependencies(self):
        '''Zope products are installed in alphabetical order. But here, we need
           ZCTextIndex to be installed before our Appy application. So, we cheat
           and force Zope to install it now.'''
        from OFS.Application import install_product
        import Products
        install_product(self.app, Products.__path__[1], 'ZCTextIndex', [], {})

    def logConnectedServers(self):
        '''Log the names of servers (LDAP, mail...) this app wants to connect
           to. Servers declared as "testable" are contacted to check the app's
           connection to it.'''
        cfg = self.config.appConfig
        servers = []
        tool = self.app.config.appy()
        # Check for connected servers
        for sv in ('ldap', 'mail', 'sso'):
            if not getattr(cfg, sv): continue
            svConfig = getattr(cfg, sv)
            enabled = svConfig.enabled and 'enabled' or 'disabled'
            # Test the connection to it
            status = ''
            if svConfig.enabled and svConfig.testable:
                status = svConfig.test(tool)
                if status: status = ', ' + status
            servers.append('%s (%s, %s%s)' % (svConfig, sv, enabled, status))
        if servers:
            self.logger.info('server(s) %s configured.' % ', '.join(servers))

    def install(self):
        self.installDependencies()
        self.patchZope()
        self.installRoles()
        self.installAppyTypes()
        self.installZopeClasses()
        self.configureSessions()
        self.installBaseObjects()
        # The following line cleans and rebuilds the catalog entirely.
        #self.app.config.appy().refreshCatalog()
        self.installCatalog()
        self.installTool()
        self.installUi()
        # Log connections to external servers (ldap, mail...)
        self.logConnectedServers()
        # Perform migrations if required
        Migrator(self).run()
        # Update Appy version in the database
        self.app.config.appy().appyVersion = appy.version.short
        # Empty the fake REQUEST object, only used at Zope startup.
        del self.app.config.getProductConfig().fakeRequest.wrappers
# ------------------------------------------------------------------------------
