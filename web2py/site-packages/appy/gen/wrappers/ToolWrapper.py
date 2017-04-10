# ------------------------------------------------------------------------------
import os.path, time
import appy
from appy.px import Px
from appy.gen.mail import sendMail
from appy.gen.wrappers import AbstractWrapper
from appy.shared.utils import executeCommand
from appy.shared.ldap_connector import LdapConnector

# ------------------------------------------------------------------------------
class ToolWrapper(AbstractWrapper):
    # --------------------------------------------------------------------------
    # Navigation-related PXs
    # --------------------------------------------------------------------------
    # Icon for hiding/showing details below the title of an object shown in a
    # list of objects.
    pxShowDetails = Px('''
     <img if="(field.name == 'title') and ztool.subTitleIsUsed(className)"
          class="clickable" src=":url('toggleDetails')"
          onclick="toggleSubTitles()"/>''')

    # Displays up/down arrows in a table header column for sorting a given
    # column. Requires variables "sortable", 'filterable' and 'field'.
    pxSortAndFilter = Px('''
     <x if="sortable">
      <img if="(sortKey != field.name) or (sortOrder == 'desc')"
           onclick=":'askBunchSorted(%s, %s, %s)' % \
                      (q(ajaxHookId), q(field.name), q('asc'))"
           src=":url('sortDown.gif')" class="clickable"/>
      <img if="(sortKey != field.name) or (sortOrder == 'asc')"
           onclick=":'askBunchSorted(%s, %s, %s)' % \
                      (q(ajaxHookId), q(field.name), q('desc'))"
           src=":url('sortUp.gif')" class="clickable"/>
     </x>
     <x if="filterable"
        var2="filterId='%s_%s' % (ajaxHookId, field.name);
              filterIdIcon='%s_icon' % filterId">
      <!-- Pressing the "enter" key in the field clicks the icon (onkeydown)-->
      <input type="text" size="7" id=":filterId"
             value=":filterKey == field.name and filterValue or ''"
             onkeydown=":'if (event.keyCode==13) document.getElementById ' \
                         '(%s).click()' % q(filterIdIcon)"/>
      <img id=":filterIdIcon" class="clickable" src=":url('funnel')"
           onclick=":'askBunchFiltered(%s, %s)' % \
                      (q(ajaxHookId), q(field.name))"/>
     </x>''')

    # Buttons for navigating among a list of objects (from a Ref field or a
    # query): next,back,first,last...
    pxNavigate = Px('''
     <div if="totalNumber &gt; batchSize" align=":dright">
      <!-- Go to the first page -->
      <img if="(startNumber != 0) and (startNumber != batchSize)"
           class="clickable" src=":url('arrowsLeft')" title=":_('goto_first')"
           onclick=":'askBunch(%s, %s, %s)' % (q(ajaxHookId), q(0), \
                                               q(batchSize))"/>

      <!-- Go to the previous page -->
      <img var="sNumber=startNumber - batchSize" if="startNumber != 0"
           class="clickable" src=":url('arrowLeft')" title=":_('goto_previous')"
           onclick=":'askBunch(%s, %s, %s)' % (q(ajaxHookId), q(sNumber), \
                                               q(batchSize))"/>

      <!-- Explain which elements are currently shown -->
      <span class="discreet"> 
       <x>:startNumber + 1</x> <img src=":url('to')"/> 
       <x>:startNumber + batchNumber</x> <b>//</b> 
       <x>:totalNumber</x>
      </span>

      <!-- Go to the next page -->
      <img var="sNumber=startNumber + batchSize" if="sNumber &lt; totalNumber"
           class="clickable" src=":url('arrowRight')" title=":_('goto_next')"
           onclick=":'askBunch(%s, %s, %s)' % (q(ajaxHookId), q(sNumber), \
                                               q(batchSize))"/>

      <!-- Go to the last page -->
      <img var="lastPageIsIncomplete=totalNumber % batchSize;
                nbOfCompletePages=totalNumber/batchSize;
                nbOfCountedPages=lastPageIsIncomplete and \
                                 nbOfCompletePages or nbOfCompletePages-1;
                sNumber= nbOfCountedPages * batchSize"
           if="(startNumber != sNumber) and \
               (startNumber != sNumber-batchSize)" class="clickable"
           src=":url('arrowsRight')" title=":_('goto_last')"
           onclick=":'askBunch(%s, %s, %s)' % (q(ajaxHookId), q(sNumber), \
                                               q(batchSize))"/>

      <!-- Go to the element number... -->
      <x var="gotoNumber=gotoNumber|False" if="gotoNumber"
         var2="sourceUrl=obj.url">:obj.pxGotoNumber</x>
     </div>''')

    # --------------------------------------------------------------------------
    # PXs for graphical elements shown on every page
    # --------------------------------------------------------------------------
    # Global elements included in every page.
    pxPagePrologue = Px('''
     <!-- Include type-specific CSS and JS -->
     <x if="cssJs">
      <link for="cssFile in cssJs['css']" rel="stylesheet" type="text/css"
            href=":url(cssFile)"/>
      <script for="jsFile in cssJs['js']"
          src=":jsFile.startswith('//') and jsFile or url(jsFile)"></script></x>

     <!-- Javascript messages -->
     <script>::ztool.getJavascriptMessages()</script>

     <!-- Global form for deleting an object -->
     <form id="deleteForm" method="post" action=":'%s/onDelete' % tool.url">
      <input type="hidden" name="uid"/>
     </form>
     <!-- Global form for deleting an event from an object's history -->
     <form id="deleteEventForm" method="post" action="do">
      <input type="hidden" name="action" value="DeleteEvent"/>
      <input type="hidden" name="objectUid"/>
      <input type="hidden" name="eventTime"/>
     </form>
     <!-- Global form for (un)linking (an) object(s) -->
     <form id="linkForm" method="post" action="do">
      <input type="hidden" name="action" value="Link"/>
      <input type="hidden" name="linkAction"/>
      <input type="hidden" name="sourceUid"/>
      <input type="hidden" name="fieldName"/>
      <input type="hidden" name="targetUid"/>
      <input type="hidden" name="semantics"/>
     </form>
     <!-- Global form for unlocking a page -->
     <form id="unlockForm" method="post" action="do">
      <input type="hidden" name="action" value="Unlock"/>
      <input type="hidden" name="objectUid"/>
      <input type="hidden" name="pageName"/>
     </form>
     <!-- Global form for generating/freezing a document from a pod template -->
     <form id="podForm" name="podForm" method="post"
           action=":'%s/doPod' % tool.url">
      <input type="hidden" name="objectUid"/>
      <input type="hidden" name="fieldName"/>
      <input type="hidden" name="template"/>
      <input type="hidden" name="podFormat"/>
      <input type="hidden" name="queryData"/>
      <input type="hidden" name="customParams"/>
      <input type="hidden" name="showSubTitles" value="true"/>
      <input type="hidden" name="checkedUids"/>
      <input type="hidden" name="checkedSem"/>
      <input type="hidden" name="mailing"/>
      <input type="hidden" name="action" value="generate"/>
     </form>''')

    pxPageBottom = Px('''
     <script var="info=zobj.getSlavesRequestInfo(page)"
             type="text/javascript">:'initSlaves(%s,%s,%s,%s)' % \
                    (q(zobj.absolute_url()), q(layoutType), info[0], info[1])
     </script>''')

    pxLiveSearchResults = Px('''
     <div var="className=req['className'];
               klass=ztool.getAppyClass(className);
               search=ztool.getLiveSearch(klass, req['w_SearchableText']);
               zobjects=ztool.executeQuery(className, search=search, \
                                           maxResults=10).objects"
          id=":'%s_LSResults' % className">
      <p if="not zobjects" class="lsNoResult">:_('query_no_result')</p>
      <div for="zobj in zobjects" style="padding: 3px 5px">
       <a href=":zobj.absolute_url()"
          var="content=ztool.truncateValue(zobj.Title(), width=80)"
          title=":zobj.Title()">:content</a>
      </div>
      <!-- Go to the page showing all results -->
      <div if="zobjects" align=":dright" style="padding: 3px">
       <a class="clickable" style="font-size: 95%; font-style: italic"
          onclick=":'document.forms[%s].submit()' % \
            q('%s_LSForm' % className)">:_('search_results_all') + '...'</a>
      </div>
     </div>''')

    pxLiveSearch = Px('''
     <form var="formId='%s_LSForm' % className"
           id=":formId" name=":formId" action=":'%s/do' % toolUrl">
      <input type="hidden" name="action" value="SearchObjects"/>
      <input type="hidden" name="className" value=":className"/>
      <table cellpadding="0" cellspacing="0"
             var="searchLabel=_('search_button')">
       <tr valign="bottom">
        <td style="position: relative">
         <input type="text" size="14" name="w_SearchableText" autocomplete="off"
                id=":'%s_LSinput' % className" class="inputSearch"
                title=":searchLabel"
                var="jsCall='onLiveSearchEvent(event, %s, %s, %s)' % \
                             (q(className), q('auto'), q(toolUrl))"
                onkeyup=":jsCall" onfocus=":jsCall"
                onblur=":'onLiveSearchEvent(event, %s, %s)' % \
                         (q(className), q('hide'))"/>
         <!-- Dropdown containing live search results -->
         <div id=":'%s_LSDropdown' % className" class="dropdown liveSearch">
          <div id=":'%s_LSResults' % className"></div>
         </div>
        </td>
        <td><input type="image" class="clickable" src=":url('search')"
                   title=":searchLabel"/></td>
       </tr>
      </table>
     </form>''')

    pxPortlet = Px('''
     <x var="toolUrl=tool.url;
             queryUrl='%s/query' % toolUrl;
             currentSearch=req.get('search', None);
             currentClass=req.get('className', None);
             currentPage=req['AUTHENTICATION_PATH'].rsplit('/',1)[-1];
             rootClasses=ztool.getRootClasses()">

      <!-- One section for every searchable root class -->
      <x for="rootClass in rootClasses" if="ztool.userMaySearch(rootClass)"
         var2="className=ztool.getPortalType(rootClass)">

       <!-- A separator if required -->
       <div class="portletSep" if="loop.rootClass.nb != 0"></div>

       <!-- Section title (link triggers the default search) -->
       <div class="portletContent"
            var="searchInfo=ztool.getGroupedSearches(rootClass)">
        <div class="portletTitle">
         <a var="queryParam=searchInfo.default and \
                            searchInfo.default.name or ''"
            href=":'%s?className=%s&amp;search=%s' % \
                   (queryUrl, className, queryParam)"
            onclick="clickOn(this)"
            class=":(not currentSearch and (currentClass==className) and \
                    (currentPage=='query')) and \
                    'current' or ''">::_(className + '_plural')</a>
         <!-- Create instances of this class -->
         <x if="ztool.userMayCreate(rootClass)"
            var2="means=ztool.getCreateMeans(rootClass)">
          <form if="means.means" class="addForm" name=":'%s_add' % className"
                var2="target=ztool.getLinksTargetInfo(rootClass)"
                action=":'%s/do' % toolUrl" target=":target.target">
           <input type="hidden" name="action" value="Create"/>
           <input type="hidden" name="className" value=":className"/>
           <input type="hidden" name="template" value=""/>
           <input type="hidden" name="popup"
                 value=":(inPopup or (target.target!='_self')) and '1' or '0'"/>
           <!-- Create from an empty form -->
           <input if="'form' in means.means" type="submit" value=""
                  var="label=_('query_create')" title=":label"
                  class="buttonSmall button" onclick=":target.openPopup"
                  style=":url('add', bg=True)"/>
           <!-- Create from a pre-filled form -->
           <a if="'template' in means.means" target="appyIFrame"
              href=":means.link">
            <input type="button" value=""
                   var="label=_('query_create_from')" title=":label"
                   class="buttonSmall button" onclick="openPopup('iframePopup')"
                   style=":url('addFrom', bg=True)"/>
           </a>
          </form>
         </x>
        </div>
        <!-- Searches -->
        <x if="ztool.advancedSearchEnabledFor(rootClass)">
         <!-- Live search -->
         <x>:tool.pxLiveSearch</x>

         <!-- Advanced search -->
         <div var="highlighted=(currentClass == className) and \
                               (currentPage == 'search')"
              class=":highlighted and 'portletSearch current' or \
                     'portletSearch'"
              align=":dright" style="margin-bottom: 4px">
          <a var="text=_('search_title')" style="font-size: 88%"
             href=":'%s/search?className=%s' % (toolUrl, className)"
             title=":text"><x>:text</x>...</a>
         </div>
        </x>

        <!-- Predefined searches -->
        <x for="search in searchInfo.searches" var2="field=search">
         <x if="search.type == 'group'">:search.px</x>
         <x if="search.type != 'group'">:search.pxView</x>
        </x>
        <!-- Portlet bottom, potentially customized by the app -->
        <x>::ztool.portletBottom(rootClass)</x>
       </div>
      </x>
     </x>''')

    # The message that is shown when a user triggers an action
    pxMessage = Px('''
     <div class=":inPopup and 'messagePopup message' or 'message'"
          style="display:none" id="appyMessage">
      <!-- The icon for closing the message -->
      <img src=":url('close')" align=":dright" class="clickable"
           onclick="this.parentNode.style.display='none'"/>
      <!-- The message content -->
      <div id="appyMessageContent"></div>
     </div>
     <script var="messages=ztool.consumeMessages()"
             if="messages">::'showAppyMessage(%s)' % q(messages)</script>''')

    # The login form
    pxLogin = Px('''
     <form id="loginForm" name="loginForm" method="post" class="login"
           action=":tool.url + '/performLogin'">
      <input type="hidden" name="js_enabled" id="js_enabled" value="0"/>
      <input type="hidden" name="cookies_enabled" id="cookies_enabled"
             value=""/>
      <input type="hidden" name="login_name" id="login_name" value=""/>
      <input type="hidden" name="pwd_empty" id="pwd_empty" value="0"/>
      <!-- Login fields directly shown or not depending on discreetLogin -->
      <span id="loginFields" name="loginFields"
            style=":cfg.discreetLogin and 'display:none' or 'display:block'">
       <span class="userStripText">:_('app_login')</span>
       <input type="text" name="__ac_name" id="__ac_name" value=""
              style="width: 142px"/>&nbsp;
       <span class="userStripText">:_('app_password')</span>
       <input type="password" name="__ac_password" id="__ac_password"
              style="width: 142px"/>
       <!-- The authentication context -->
       <x if="cfg.authContext" var2="ctx=cfg.authContext">
        <span class="userStripText">:_('login_context')</span>
        <select id="__ac_ctx" name="__ac_ctx"
                var="ctxDefault=ctx.getDefaultContext(tool)">
         <option value="">:_('choose_a_value')</option>
         <option for="ctxOption in ctx.getContexts(tool)" value=":ctxOption[0]"
                 selected=":ctxOption[0] == ctxDefault">:ctxOption[1]</option>
        </select>
       </x>
       <!-- The "submit" button -->
       <input type="submit" name="submit" onclick="setLoginVars()"
              var="label=_('app_connect')" value=":label" alt=":label"/>
       <input type="hidden" name="goto" value=":req.get('goto', None)"/>
       <!-- Forgot password ? -->
       <a if="ztool.showForgotPassword()"
          href="javascript: openPopup('askPasswordReinitPopup')"
          class="lostPassword">:_('forgot_password')</a>
       <!-- Hide the strip -->
       <img if="cfg.discreetLogin" src=":url('close')"
            onclick="toggleLoginForm(false)" class="clickable"/>
      </span>
     </form>''')

    # The page footer
    pxFooter = Px('''<span class="footerContent">::_('footer_text')</span>''')

    # Hooks for defining a PX that proposes additional links, before and after
    # the links corresponding to top-level pages.
    pxLinks = Px('')
    pxLinksAfter = Px('')

    # Hook for defining a PX that proposes additional icons after standard
    # icons in the user strip.
    pxIcons = Px('')

    pxHome = Px('''
     <table>
      <tr valign="middle">
       <td align="center">::_('front_page_text')</td>
      </tr>
     </table>''', template=AbstractWrapper.pxTemplate, hook='content')

    # Error 404: page not found
    px404 = Px('''<div>:msg</div>
     <div if="not isAnon and not inPopup">
      <a href=":ztool.getSiteUrl()">:_('app_home')</a>
     </div>''', template=AbstractWrapper.pxTemplate, hook='content')

    # Error 403: unauthorized
    px403 = Px('''<div>
     <img src=":url('fake')" style="margin-right: 5px"/><x>:msg</x></div>''',
     template=AbstractWrapper.pxTemplate, hook='content')

    # Error 500: server error
    px500 = Px('''<div>
     <img src=":url('warning')" style="margin-right: 5px"/><x>:msg</x></div>
     <!-- Show the traceback for admins -->
     <x if="showTraceback">::error_traceback</x>''',
     template=AbstractWrapper.pxTemplate, hook='content')

    pxQuery = Px('''
     <div var="className=req['className'];
               searchName=req.get('search', '');
               uiSearch=ztool.getSearch(className, searchName, ui=True);
               klass=ztool.getAppyClass(className);
               resultModes=uiSearch.getAllResultModes(klass);
               rootHookId=uiSearch.getRootHookId();
               cssJs=None"
          id=":rootHookId">
      <script>:uiSearch.getCbJsInit(rootHookId)</script>
      <x>:tool.pxPagePrologue</x>
      <div align=":dright" if="len(resultModes) &gt; 1">
       <select name="px"
               onchange=":'switchResultMode(this, %s)' % q('queryResult')">
        <option for="mode in resultModes"
                value=":mode">:uiSearch.getModeText(mode, _)</option>
       </select>
      </div>
      <x>:uiSearch.pxResult</x>
     </div>''', template=AbstractWrapper.pxTemplate, hook='content')

    pxSearch = Px('''
     <x var="className=req['className'];
             refInfo=req.get('ref', None);
             searchInfo=ztool.getSearchInfo(className, refInfo);
             cssJs={};
             layoutType='search';
             x=ztool.getCssJs(searchInfo.fields, 'edit', cssJs)">

      <!-- Include type-specific CSS and JS -->
      <link for="cssFile in cssJs['css']" rel="stylesheet" type="text/css"
            href=":url(cssFile)"/>
      <script for="jsFile in cssJs['js']" src=":url(jsFile)"></script>

      <!-- Search title -->
      <h1><x>:_('%s_plural'%className)</x> &ndash;
          <x>:_('search_title')</x></h1>
      <!-- Form for searching objects of request/className -->
      <form name="search" action=":ztool.absolute_url()+'/do'" method="post">
       <input type="hidden" name="action" value="SearchObjects"/>
       <input type="hidden" name="className" value=":className"/>
       <input if="refInfo" type="hidden" name="ref" value=":refInfo"/>

       <table class="searchFields">
        <tr for="searchRow in ztool.getGroupedSearchFields(searchInfo)"
            valign="top">
         <td for="field in searchRow" class="search"
             var2="scolspan=field and field.scolspan or 1"
             colspan=":scolspan"
             width=":'%d%%' % ((100/searchInfo.nbOfColumns)*scolspan)">
           <x if="field">:field.pxRender</x>
           <br class="discreet"/>
         </td>
        </tr>
       </table>

       <!-- Submit button -->
       <input var="label=_('search_button');
                   css=ztool.getButtonCss(label, small=False)" type="submit"
              class=":css" value=":label" style=":url('search', bg=True)"/>
      </form>
     </x>''', template=AbstractWrapper.pxTemplate, hook='content')

    pxBack = Px('''
     <html>
      <head><script src=":ztool.getIncludeUrl('appy.js')"></script></head>
      <body><script>backFromPopup()</script></body>
     </html>''')

    def isToolWriter(self):
        '''Some tool elements are only accessible to tool writers
           (ie Managers).'''
        if self.allows('write'): return 'view'

    def computeConnectedUsers(self):
        '''Computes a table showing users that are currently connected.'''
        res = '<table cellpadding="0" cellspacing="0" class="list compact">' \
              '<tr><th></th><th>%s</th></tr>' % \
              self.translate('last_user_access')
        rows = []
        from DateTime import DateTime
        for userId, lastAccess in self.o.loggedUsers.items():
            user = self.search1('User', noSecurity=True, login=userId)
            if not user: continue # Could have been deleted in the meanwhile
            access = DateTime(lastAccess)
            rows.append('<tr><td><a href="%s">%s</a></td><td>%s</td></tr>' % \
                        (user.url, user.title, self.formatDate(access)))
        return res + '\n'.join(rows) + '</table>'

    def getObject(self, uid):
        '''Allow to retrieve an object from its unique identifier p_uid'''
        return self.o.getObject(uid, appy=True)

    def getDiskFolder(self):
        '''Returns the disk folder where the Appy application is stored'''
        return self.o.config.diskFolder

    def getClass(self, zopeName):
        '''Gets the Appy class corresponding to technical p_zopeName'''
        return self.o.getAppyClass(zopeName)

    def getAvailableLanguages(self):
        '''Returns the list of available languages for this application'''
        return [(t.id, t.title) for t in self.translations]

    def convert(self, fileName, format):
        '''Launches a UNO-enabled Python interpreter as defined in the tool for
           converting, using LibreOffice in server mode, a file named p_fileName
           into an output p_format.'''
        convScript = '%s/pod/converter.py' % os.path.dirname(appy.__file__)
        cfg = self.o.getProductConfig(True)
        cmd = [cfg.unoEnabledPython, convScript, fileName, format,
               '-p%d' % cfg.libreOfficePort]
        self.log('executing %s...' % str(cmd))
        return executeCommand(cmd) # The result is a tuple (s_out, s_err)

    def sendMail(self, to, subject, body, attachments=None):
        '''Sends a mail. See doc for appy.gen.mail.sendMail'''
        mailConfig = self.o.getProductConfig(True).mail
        sendMail(mailConfig, to, subject, body, attachments=attachments,
                 log=self.log)

    def formatDate(self, date, format=None, withHour=True, language=None):
        '''Check doc @ToolMixin::formatDate'''
        if not date: return
        return self.o.formatDate(date, format, withHour, language)

    def now(self, format=None):
        '''Returns the current date/hour as a DateTime instance. If p_format is
           specified, it returns a formatted date instead.'''
        from DateTime import DateTime
        res = DateTime()
        if format: res = res.strftime(format)
        return res

    def getUserName(self, login=None, normalized=False):
        return self.o.getUserName(login=login, normalized=normalized)

    def refreshCatalog(self, startObject=None, onlyUID=False):
        '''Reindex all Appy objects, or only those starting at p_startObject.
           If p_onlyUID is True, a single index (UID) is recomputed. Else, all
           the other indexes are recomputed, this one excepted.'''
        indexes = ['UID']
        exclude = not onlyUID
        if not startObject:
            # All database objects must be reindexed
            app = self.o.getParentNode()
            if not onlyUID:
                # Starts by clearing the catalog
                self.log('recomputing the whole catalog ' \
                         '(starts by clearing it)...')
                app.catalog._catalog.clear()
                self.log('catalog cleared.')
                # Reindex special index UID for all objects. Indeed, other
                # indexes may depend on the links between objects, which are
                # implemented via this index.
                self.refreshCatalog(onlyUID=True)
                self.log('reindexing all indexes but "UID" for every object...')
            else:
                self.log('reindexing "UID" for every object...')
            # Reindex all Appy objects (in folders "config" and "data")
            nb = 1
            failed = []
            for folder in ('config', 'data'):
                for obj in getattr(app, folder).objectValues():
                    subNb, subFailed = self.refreshCatalog(startObject=obj,
                                                           onlyUID=onlyUID)
                    nb += subNb
                    failed += subFailed
                if folder == 'config':
                    try: # Reindex the tool itself
                        app.config.reindex(indexes=indexes, exclude=exclude)
                    except Exception:
                        failed.append(app.config)
            # Try to re-index all objects for which reindexation has failed
            for obj in failed: obj.reindex(indexes=indexes, exclude=exclude)
            failMsg = failed and ' (%d retried)' % len(failed) or ''
            self.log('%d object(s) reindexed%s.' % (nb, failMsg))
        else:
            nb = 1
            failed = []
            for obj in startObject.objectValues():
                subNb, subFailed = self.refreshCatalog(startObject=obj,
                                                       onlyUID=onlyUID)
                nb += subNb
                failed += subFailed
            try:
                startObject.reindex(indexes=indexes, exclude=exclude)
            except Exception, e:
                failed.append(startObject)
            return nb, failed

    def oldRefreshCatalog(self, startObject=None):
        '''Reindex all Appy objects. For some unknown reason, method
           catalog.refreshCatalog is not able to recatalog Appy objects.'''
        if not startObject:
            # This is a global refresh. Clear the catalog completely, and then
            # reindex all Appy-managed objects, ie those in folders "config"
            # and "data".
            # First, clear the catalog.
            self.log('recomputing the whole catalog...')
            app = self.o.getParentNode()
            app.catalog._catalog.clear()
            nb = 1
            failed = []
            for obj in app.config.objectValues():
                subNb, subFailed = self.refreshCatalog(startObject=obj)
                nb += subNb
                failed += subFailed
            try:
                app.config.reindex()
            except:
                failed.append(app.config)
            # Then, refresh objects in the "data" folder
            for obj in app.data.objectValues():
                subNb, subFailed = self.refreshCatalog(startObject=obj)
                nb += subNb
                failed += subFailed
            # Re-try to index all objects for which reindexation has failed
            for obj in failed: obj.reindex()
            if failed:
                failMsg = ' (%d retried)' % len(failed)
            else:
                failMsg = ''
            self.log('%d object(s) reindexed%s.' % (nb, failMsg))
        else:
            nb = 1
            failed = []
            for obj in startObject.objectValues():
                subNb, subFailed = self.refreshCatalog(startObject=obj)
                nb += subNb
                failed += subFailed
            try:
                startObject.reindex()
            except Exception, e:
                failed.append(startObject)
            return nb, failed

    def _login(self, login):
        '''Performs a login programmatically. Used by the test system'''
        self.request.user = self.search1('User', noSecurity=True, login=login)

    def doSynchronizeExternalUsers(self):
        '''Synchronizes the local User copies with a distant LDAP user base'''
        cfg = self.o.getProductConfig(True).ldap
        if not cfg: raise Exception('LDAP config not found.')
        counts = cfg.synchronizeUsers(self)
        msg = 'LDAP users: %d created, %d updated, %d untouched, ' \
              '%d invalid entries.' % counts
        return True, msg

    def showSynchronizeUsers(self):
        '''Show this button only if a LDAP connection exists and is enabled.'''
        cfg = self.o.getProductConfig(True).ldap
        if cfg and cfg.enabled: return 'view'

    def mayDelete(self):
        '''No one can delete the tool.'''
        return
# ------------------------------------------------------------------------------
