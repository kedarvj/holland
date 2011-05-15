"""
    holland.core.stream.plugin
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    This module provides the basic methods for the stream API

    :copyright: 2010-2011 Rackspace US, Inc.
    :license: BSD, see LICENSE.rst for details
"""

import os
try:
    _set = set
except NameError: #pragma: no cover
    from sets import Set as _set

from holland.core.plugin import BasePlugin, PluginError, \
                                load_plugin, iterate_plugins


def load_stream_plugin(name):
    """Load a stream plugin by name"""
    return load_plugin('holland.stream', name)

def available_methods():
    """List available backup methods as strings

    These names are suitable for passing to open_stream(..., method=name, ...)
    """
    results = []
    for plugin in _set(iterate_plugins('holland.stream')):
        results.append(plugin.name)
        results.extend(plugin.aliases)
    return results

def open_stream_wrapper(basedir, *args, **kwargs):
    """A wrapper to open all file relative to some base path and dispatch to
    ``open_stream``

    :returns: function
    """
    def dispatch(filename, mode='r'):
        """Dispatch to open_stream with the args/kwargs provided to the
        open_stream_wrapper method.

        :returns: File-like object from open-stream
        """
        filename = os.path.join(basedir, filename)
        return open_stream(filename, mode, *args, **kwargs)
    return dispatch

def open_stream(filename, mode='r', method=None, *args, **kwargs):
    """Open a stream with the provided method

    If not method is provided, this will default to the builtin file
    object
    """
    if method is None:
        method = 'builtin'
    try:
        stream = load_stream_plugin(method)
    except PluginError, exc:
        raise IOError("No stream found for method %r: %s" % (method, exc))
    return stream.open(filename, mode, *args, **kwargs)

class StreamPlugin(BasePlugin):
    """Base Plugin class"""
    name = ''
    aliases = ()

    def open(self, name, mode, *args, **kwargs):
        """Open a stream and return a FileLike instance"""
        return open(name, mode, *args, **kwargs)

    def stream_info(self, name, method, *args, **kwargs):
        """Provide information about this stream"""
        return dict(
            extension='',
            name=name,
            method=method,
            description="%s: args=%r kwargs=%r" % (self.__class__.__name__,
                                                   args, kwargs)
        )


class StreamError(IOError):
    """Exception in stream"""
