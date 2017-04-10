# ------------------------------------------------------------------------------
from appy import Object
from dav import Resource

# Error management -------------------------------------------------------------
class GoogleError(Exception): pass
SERVER_ERROR = 'Server error: %s.'
STATUS_ERROR = 'Status error: %s.'
RESOURCE_ERROR = 'Resource error: %s.'

# ------------------------------------------------------------------------------
class Address:
    '''Represents an address as geolocalized by Google'''
    def __init__(self, result):
        self.address = result.formatted_address
        coordinates = result.geometry.location
        self.coordinates = coordinates.lat, coordinates.lng

    def __repr__(self):
        return '%s (%f,%f)' % (self.address,
                               self.coordinates[0], self.coordinates[1])

# ------------------------------------------------------------------------------
class Google:
    '''Represents the Google Web Services API'''
    Error = GoogleError

    # URLs to the currently supported Google APIs
    mapsApi = 'http://maps.googleapis.com/maps/api'
    apis = Object(
      geocoding='%s/geocode' % mapsApi,
      distance='%s/distancematrix' % mapsApi
    )

    @staticmethod
    def _call(logger, url):
        '''Sends a HTTP request to Google'''
        logger.log('ask Google: %s' % url)
        server = Resource(url)
        try:
            response = server.get()
        except Resource.Error, re:
            msg = RESOURCE_ERROR % str(re)
            logger.log(msg, type='error')
            raise GoogleError(msg)
        # We got a response
        if response.code != 200:
            msg = SERVER_ERROR % response.text
            logger.log(msg, type='error')
            raise GoogleError(msg)
        # Check the return status
        status = response.data['status']
        if status != 'OK':
            msg = STATUS_ERROR % status
            logger.log(msg, type='error')
            raise GoogleError(msg)
        return response.data

    @staticmethod
    def geocode(logger, address, verbose=False):
        '''Returns the coordinates of some given p_address. If p_verbose is
           False, it returns a tuple ~(f_latitude, f_longitude)~. Else, it
           returns the complete data structure as described in the Google
           API.'''
        # Encode p_address
        address = address.replace(' ', '+').replace('\t', '')
        # Perform the HTTP request
        url = '%s/json?address=%s' % (Google.apis.geocoding, address)
        data = Google._call(logger, url)
        # Return the complete response when required
        if verbose: return data
        # Return the coordinates and formatted addresses only
        results = data.results
        if len(results) == 1: # A single match
            res = Address(results[0])
            msg = 'got one match: %s' % res
        else:
            res = [Address(result) for result in results]
            msg = 'got %d matches.' % len(res)
        logger.log(msg)
        return res

    @staticmethod
    def distance(logger, origin, destination, mode='driving', language='fr',
                 verbose=False):
        '''Returns the distance between p_origin and p_destination (expressed
           as tuples of floats (latitude, longitude).'''
        # Encode parameters
        params = 'origins=%s&destinations=%s&mode=%s&language=%s' % \
                 (str(origin)[1:-1].replace(' ', ''),
                  str(destination)[1:-1].replace(' ', ''), mode, language)
        # Perform the HTTP request
        url = '%s/json?%s' % (Google.apis.distance, params)
        data = Google._call(logger, url)
        # Return the complete response when required
        if verbose: return data
        res = data.rows[0].elements[0].distance.value
        logger.log('response is %dm' % res)
        return res
# ------------------------------------------------------------------------------
