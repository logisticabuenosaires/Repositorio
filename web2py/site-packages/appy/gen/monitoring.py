# ------------------------------------------------------------------------------
import os, appy

# ------------------------------------------------------------------------------
class Monitoring:
    '''Implements stuff allowing to perform monitoring on a Appy application.
       * URL <yourapp>/config/check can be called to get monitoring info;
       * Configure monitoring parameters by updating attributes of the
         Monitoring instance defined in the Config class.'''
    def __init__(self):
        # When returning a success status code, what code to return ?
        self.ok = 'OK'
        # When returning a failure status code, what code to return ?
        self.ko = 'KO'
        # Do we check the presence of LibreOffice running in server mode ?
        self.checkLo = True

    def get(self, request, config):
        '''Returns monitoring-related info'''
        # The global monitoring status
        success = True
        # Check if LibreOffice is running
        if self.checkLo:
            loLine = ''
            null, out = os.popen4('ps -ef | grep "soffice"')
            for line in out.readlines():
                if "accept=socket" in line:
                    loLine = line
                    break
            if not loLine:
                success = False
        # Do we need to return complete information or only a status code?
        status = success and self.ok or self.ko
        if 'all' not in request: return status
        # Return complete information
        res = ['Status: %s\n' % status, 'Appy version: %s' % appy.getVersion()]
        if self.checkLo:
            # Appy parameters for connecting to LibreOffice in server mode
            res.append('UNO-enabled Python: %s' % \
                       config.unoEnabledPython or '<not specified>')
            res.append('LibreOffice configured@port %d'% config.libreOfficePort)
            # Info about the running LibreOffice server
            if not loLine:
                res.append('LibreOffice not found')
            else:
                res.append('LibreOffice found:\n%s' % loLine)
        return '\n'.join(res)
# ------------------------------------------------------------------------------
