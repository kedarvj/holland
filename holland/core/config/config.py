import os
import re
import codecs
import logging
from holland.core.util.datastructures import SortedDict as OrderedDict

LOG = logging.getLogger(__name__)

class ConfigError(Exception):
    """General error when processing config"""

class ConfigSyntaxError(ConfigError, SyntaxError):
    """Syntax error when processing config"""

class BaseFormatter(object):
    """Format values in a config file"""
    def format(self, key, value):
        # only return strings
        if isinstance(value, basestring):
            return value
        return None

class Config(OrderedDict):
    """Simple ini config"""
    section_cre     = re.compile(r'\s*\[(?P<name>[^]]+)\]\s*(?:#.*)?$')
    key_cre         = re.compile(r'(?P<key>[^:=\s\[][^:=]*)=\s*(?P<value>.*)$')
    value_cre       = re.compile(r'(?P<value>(?:[^"\\#]|\\.|'
                                 r'"(?:[^"\\]*(?:\\.[^"\\]*)*)")*)')
    empty_cre       = re.compile(r'\s*($|#|;)')
    cont_cre        = re.compile(r'\s+(?P<value>.+?)$')
    include_cre     = re.compile(r'%include (?P<name>.+?)\s*$')

    #: an object that's always asked when formatting a key/value pair
    formatter       = BaseFormatter()

    #: dict mapping keys to source file/lines
    source          = ()

    def __init__(self, *args, **kwargs):
        super(Config, self).__init__(*args, **kwargs)
        self.source = {}

    #@classmethod
    def parse(cls, iterable):
        """Parse a sequence of lines and return the resulting ``Config`` instance.

        :param iterable: any iterable object that yield lines of text
        :returns: new ``Config`` instance
        """
        cfg = cls()
        section = cfg
        name = getattr(iterable, 'name', '<unknown>')
        key = None
        for lineno, line in enumerate(iterable):
            if cls.empty_cre.match(line):
                continue
            m = cls.section_cre.match(line)
            if m:
                sectname = m.group('name')
                try:
                    section = cfg[sectname]
                except KeyError:
                    cfg[sectname] = cls()
                    section = cfg[sectname]
                LOG.info("Recording source of section '%s' as %s:%d",
                         sectname, name, lineno + 1)
                cfg.source[sectname] = '%s:%d' % (name, lineno + 1)
                key = None # reset key
                continue
            m = cls.key_cre.match(line)
            if m:
                key, value = m.group('key', 'value')
                key = cfg.optionxform(key.strip())
                value = cfg.valuexform(value)
                section[key] = value
                LOG.info("Recording source of key '%s' as %s:%d",
                         key, name, lineno + 1)
                section.source[key] = '%s:%d' % (name, lineno + 1)
                continue
            m = cls.cont_cre.match(line)
            if m:
                if not key:
                    raise ConfigError("unexpected continuation line")
                section[key] += line.strip()
                if '-' not in section.source[key]:
                    LOG.info("Recording source of key '%s' as %s-%d",
                             key, section.source[key], lineno + 1)
                    section.source[key] += '-%d' % (lineno+1)
                else:
                    src_info = section.source[key].split('-')[0]
                    LOG.info("Recording source of key '%s' as %s-%d",
                             key, src_info, lineno + 1)
                    section.source[key] = src_info + '-%d' % (lineno + 1)
                continue
            m = cls.include_cre.match(line)
            if m:
                path = m.group('name')
                if not os.path.isabs(path):
                    base_path = os.path.dirname(getattr(iterable, 'name', '.'))
                    path = os.path.join(base_path, path)
                subcfg = cls.read([path])
                cfg.merge(subcfg)
                continue
            # XXX: delay to end
            raise ConfigSyntaxError("Invalid line",
                                    (getattr(iterable, 'name', '<unknown>'),
                                     0,
                                     lineno,
                                     line))
        return cfg
    parse = classmethod(parse)

    #@classmethod
    def read(cls, filenames, encoding='utf8'):
        """Read and parse a list of filenames.

        :param filenames: list of filenames to load
        :param encoding: character set encoding of each config file
        :returns: config instance
        """
        main = cls()
        for path in filenames:
            fileobj = codecs.open(path, 'r', encoding=encoding)
            try:
                cfg = cls.parse(fileobj)
            finally:
                fileobj.close()
            main.merge(cfg)
        return main
    read = classmethod(read)

    def merge(self, src_config):
        """Merge another config instance with this one.

        Merging copies all options and subsections from the source config,
        ``src_config``, into this config. Options from ``src_config`` will
        overwrite existing options in this config.

        :param src_config: ``Config`` instance to merge into this instance
        :returns: self
        """
        for key, value in src_config.iteritems():
            if isinstance(value, Config):
                try:
                    section = self[key]
                    if not isinstance(section, Config):
                        # attempting to overwrite a normal key=value with a
                        # section
                        raise TypeError('value-namespace conflict')
                except KeyError:
                    section = self.__class__()
                    self[key] = section
                section.merge(value)
            else:
                self[key] = value
        self.source.update(src_config.source)

    def meld(self, config):
        """Meld another config instance with this one.

        Merging copies all options and subsections from the source config,
        ``src_config``, into this config. Unlike ``merge()``, existing options
        in this config will always be preserved - ``meld()`` only adds new
        options.

        :param src_config: ``Config`` instance to meld into this instance
        :returns: self
        """
        for key, value in config.iteritems():
            if isinstance(value, Config):
                try:
                    section = self[key]
                    if not isinstance(section, Config):
                        # attempting to overwrite a normal key=value with a
                        # section
                        raise TypeError('value-namespace conflict')
                except KeyError:
                    section = self.__class__()
                    self[key] = section
                    self.source[key] = config.source[key]
                section.meld(value)
            else:
                try:
                    self[key]
                except KeyError:
                    # only add the value if it does not already exist
                    self[key] = value
                    self.source[key] = value

    def write(self, path, encoding='utf8'):
        """Write a representaton of the config to the specified filename.

        The target filename will be written with the requested encoding.
        ``filename`` can either be a path string or any file-like object with
        a ``write(data)`` method.

        :param path: filename or file-like object to serialize this config to
        :param encoding: encoding to writes this config as
        """
        try:
            write = path.write
            write(str(self))
        except AttributeError:
            fileobj = codecs.open(path, 'w', encoding=encoding)
            try:
                fileobj.write(str(self))
            finally:
                fileobj.close()

    def optionxform(self, option):
        """Transforms the option name ``option``

        This method should be overriden in subclasses that want to alter
        the default behavior.

        :param option: option name
        :returns: tranformed option
        """
        return str(option)

    def valuexform(self, value):
        """Transform a value in an option = value pair

        This method defaults to stripping an inline comment
        from the end of a value
        """
        match = self.value_cre.match(value)
        end = match.end()
        if value[end:end+1] and value[end:end+1] != '#':
            raise ValueError(value)
        return match.group('value').strip()

    def sectionxform(self, section):
        """Transforms the section name ``section``

        This method should be overriden in subclasses that want to alter
        the default behavior.

        :param section: section name
        :returns: transformed section name
        """
        return str(section)

    def __setitem__(self, key, value):
        if isinstance(value, dict) and not isinstance(value, self.__class__):
            value = self.__class__(value)
        if isinstance(value, self.__class__):
            key = self.sectionxform(key)
        elif isinstance(value, basestring):
            key = self.optionxform(key)
        super(Config, self).__setitem__(key, value)

    def __str__(self):
        """Convert this config to a string"""
        lines = []
        for key, value in self.iteritems():
            if isinstance(value, Config):
                lines.append("[%s]" % key)
                lines.append(str(value))
                lines.append("")
            else:
                value = self.formatter.format(key, value)
                if value is not None:
                    lines.append("%s = %s" % (key, value))
        return os.linesep.join(lines)

    def __repr__(self):
        return "%s(%s)" % (self.__class__.__name__,
                           dict.__repr__(self))
