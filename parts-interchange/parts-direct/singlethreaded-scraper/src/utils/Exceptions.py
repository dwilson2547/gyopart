
class NoProgressException(Exception):
    pass

class MissingFromCacheException(Exception):
    pass

class TreeBuilderError(Exception):
    pass

class PageRetrievalError(Exception):
    pass

class Browser403Error(Exception):
    pass

class Browser429Error(Exception):
    pass

class InternetDownError(Exception):
    pass