#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Backend Authentication Module to allow connect to AD (and LDAP) in the future
"""
_author__ = "Roch Auburtin"
__copyright__ = "Copyright 2013, TODO"
__credits__ = ["Christian Hammond from the The Review Board Project"]

import os
import sys
import logging
import unittest
from config import Config
from utils import str2bool
import getpass
import time

#Suffix added to the last name when the user is imported from AD
AD_SUFFIX='(AD)'


class ActiveDirectoryBackend:
    """Authenticate a user against an Active Directory server."""
    #based on
    #https://github.com/reviewboard/reviewboard/blob/master/reviewboard/accounts/backends.py
    def get_domain_name(self):
        return str(Config.auth_ad_domain_name)

    def get_ldap_search_root(self):
        if getattr(Config, "auth_ad_search_root", None):
            root = [Config.auth_ad_search_root]
        else:
            root = ['dc=%s' % x for x in self.get_domain_name().split('.')]
            #limit to the OU specified by ad_ou_name if defined
            if Config.auth_ad_ou_name:
                root = ['ou=%s' % Config.auth_ad_ou_name] + root
        return ','.join(root)

    def search_ad(self, con, filterstr):
        import ldap
        search_root = self.get_ldap_search_root()
        logging.debug('Search root ' + search_root)
        return con.search_s(search_root, scope=ldap.SCOPE_SUBTREE,
                filterstr=filterstr)

    def can_recurse(self, depth):
        #to avoid very long recursive search, it is a good idea to limit the 
        #recursive depth
        return (int(Config.auth_ad_recursion_depth) == -1 or
                depth <= int(Config.auth_ad_recursion_depth))

    def get_member_of(self, con, search_results, seen=None, depth=0):
        depth += 1
        if seen is None:
            seen = set()

        for name, data in search_results:
            #print "name",name,"data",data
            if name is None:
                continue
            member_of = data.get('memberOf', [])
            logging.debug("member_of %s" % member_of)
            #print "member_of", member_of
            new_groups = [x.split(',')[0].split('=')[1] for x in member_of]
            old_seen = seen.copy()
            seen.update(new_groups)

            # collect groups recursively
            if self.can_recurse(depth):
                for group in new_groups:
                    if group in old_seen:
                        continue
                    # Search for groups with the specified CN. Use the CN
                    # rather than The sAMAccountName so  that behavior is 
                    # correct when the values differ (e.g. if a
                    # "pre-Windows 2000" group name is set in AD)
                    group_data = self.search_ad(con,'(&(objectClass=group)(cn=%s))' % group)
                    seen.update(self.get_member_of(con, group_data, seen=seen, depth=depth))
            else:
                logging.warning('ActiveDirectory recursive group check reached maximum recursion depth.')

        return seen


    def authenticate(self, username, password):
        import ldap
        #use generally ad_uid_mask=(sAMAccountName=%s) in the settings
        #to get the record based on the login in AD
        uid = Config.auth_ad_uid_mask % username

        try:
            dc=('389', Config.auth_ad_domain_controller)
            port, host = dc
            #print "port",port,"host",":"+host+":"
            ldapo = ldap.open(host,port=int(port))
            
            #TODO: need to test it
            if str2bool(Config.auth_ad_use_tls):
                ldapo.start_tls_s()
            
            #Very important to speed ldap searching with AD
            #set to 0 to turn off "chasing referrels"
            ldapo.set_option(ldap.OPT_REFERRALS, 0)

            #build the correct login name
            if "@%s"%self.get_domain_name() in username:
                bind_username = username
            else:
                bind_username ='%s@%s' % (username, self.get_domain_name())
            
            #here, we test authentication
            ldapo.simple_bind_s(bind_username,password)

            #print "uid:%s" % uid
            user_data = self.search_ad(ldapo, '(&(objectClass=user)%s)' % uid)
            #print "user_data",user_data

            try:
                group_names = self.get_member_of(ldapo, user_data)
                #print "group_names",group_names
            except Exception, e:
                logging.error("Active Directory error: failed getting groups"
                        " for user '%s': %s" % (username,e))
                return None
            
            #we test if the user is a member of the ad required group if defined in the settings
            required_group = Config.auth_ad_required_group_name
            if required_group and not required_group in group_names:
                logging.warning("Active Directory: User %s is not in required group %s" % (username, required_group))
                return None

            #return the username
            return username

        except ldap.SERVER_DOWN:
            logging.warning('Active Directory: Domain controller is down')
        except ldap.INVALID_CREDENTIALS:
            logging.warning('Active Directory: Failed login for user %s' % username)
            return None
        except ldap.LDAPError, e:
            logging.warning('LDAP error: %s' % e)
        except:
            logging.warning('An error while LDAP-authenticating: %r' %
                    sys.exc_info()[1])

        logging.error('Active Directory error: Could not contact any domain controller servers')
        return None


class TestActiveDirectoryBackend(unittest.TestCase):
    def setUp(self):
        pass

    def test0_authenticate(self):
        #print 'skip test test0_repository'
        #return
        
        #Attention when testing with AD,
        #By default, AD allow connection with the old password for
        #one hour, to set to O
        #follow http://support.microsoft.com/kb/906305/en-us (works on windows 2012)
        #To change the lifetime period of an old password, 
        #add a DWORD entry that is named OldPasswordAllowedPeriod to the following registry subkey on a domain controller:
        #HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Lsa
        #create the value if not defined (DWORD) with 0
        
        #Be sure also to be able to connect with the user
        #See http://superuser.com/questions/209204/how-to-grant-remote-desktop-right-to-a-user-in-windows-server-2008
        #gpedit.msc => Computer Config > Windows Settings > Security Settings > Local Policies > User Rights Assignment. 
        #Find the entry for "Allow log on through remote desktop services" and "deny log on through remote desktop services",
        #and see if the groups in question are in either of those categories. Deny permissions will usually override allow permissions

        auth =  ActiveDirectoryBackend()
        username=raw_input('Username: ')
        password=getpass.getpass()
        t1=time.time()
        user = auth.authenticate(username,password)
        t2=time.time()
        self.assertTrue(user is not None, 
                        "No authentication with user:%s: password:%s:"
                        " check settings and the credentials"
                        % (username, password))
        if user:
            print 'connected with %s in %f sec' % (user,t2-t1)


if __name__ == '__main__':
        suite = unittest.TestLoader().loadTestsFromTestCase(TestActiveDirectoryBackend)
        unittest.TextTestRunner(verbosity=2).run(suite)
