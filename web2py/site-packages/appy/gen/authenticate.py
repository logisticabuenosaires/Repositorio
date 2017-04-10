'''Authentication-related stuff'''

# ------------------------------------------------------------------------------
class AuthenticationContext:
    '''When an application uses an authentication context, its users, when
       logging in, must, besides their login and password, choose a context
       among possible authentication contexts. Then, your application has access
       to the chosen context via the request attribute "authContext".

       If you want to use authentication contexts in your Appy application, you
       must create a class that inherits from this one and overrides some of its
       methods (see below). Then, in your Config instance (appy.gen.Config),
       set an instance of your class in attribute "authContext".
    '''

    def isMandatory(self, tool):
        '''When authentication contexts are activated, is the user forced to
           choose one ?'''
        return True # By default, yes

    def getContexts(self, tool):
        '''Returns the application-specific authentication contexts, as a list
           of tuples (s_context, s_name). s_context is a short string that
           identifies the context, while s_name is a human-readable name that
           will be shown in the UI.'''

    # This method does not need to be overridden if there is no default context
    def getDefaultContext(self, tool):
        '''Returns the default context among contexts as returned by
           m_getContexts.'''

    # This method must not be overridden
    def getName(self, tool, context):
        '''Returns the name of some given p_context'''
        for ctx, name in self.getContexts(tool):
            if ctx == context:
                return name
# ------------------------------------------------------------------------------
