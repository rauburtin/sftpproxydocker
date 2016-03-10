#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
import ConfigParser
from optparse import OptionParser

class ConfigError(Exception):
    pass
class Config(object):
    @staticmethod
    def get_config_ini():
        config_path = None
        for loc in (os.environ.get("TEST-LDAP_CONF"),
                "/etc/test-ldap",
                os.path.join(os.path.expanduser("~"),".test-ldap"),
                os.path.expanduser("~"),
                os.curdir,
                os.path.dirname(__file__)):
                if loc:
                    config_path = os.path.join(loc,"config.ini")
                    if os.path.exists(config_path):
                        return config_path
        return None
    
    @staticmethod
    def read():
        try: 
            config = ConfigParser.ConfigParser()
            config.read(Config.get_config_ini())

            if config.has_section('mysql'):
                for option in config.options('mysql'):
                    setattr(Config,'mysql_'+option,config.get('mysql',option))

            if config.has_section('auth'):
                for option in config.options('auth'):
                    setattr(Config,'auth_'+option,config.get('auth',option))

        except ConfigParser.NoSectionError:
            raise ConfigError('Impossible to read the config file :%s.' %\
                    Config.get_config_ini())

Config.read()
def get_config_attr(name):
    return getattr(Config,name)

def get_config_attrs(names,update_config=False):
    if update_config:
        Config.update__config()

    config_attrs={}
    for name in names:
        config_attrs[name]=getattr(Config,name)

    return config_attrs

if __name__=='__main__':

    usage = "usage: %prog [options]"
    parser = OptionParser(usage)
    parser.add_option("-q", "--quiet", dest="display",
                      help="quiet", action="store_false",default=True)
    (options, args) = parser.parse_args()
    if options.display:
        Config.read()
        for attribute in [attr for attr in dir(Config) if not attr.startswith('__')
                and not callable(getattr(Config,attr))]:
            print attribute, getattr(Config,attribute)
    

