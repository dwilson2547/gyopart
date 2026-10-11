
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

class SiteUnavailableError(Exception):
    """The site served a maintenance page, a 5xx, or a bot challenge that didn't clear. Transient:
    stop the run and retry later. Never cache the page or mark anything done on it."""
