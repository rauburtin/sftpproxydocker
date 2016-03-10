#!/usr/bin/env python
# -*- coding: utf-8 -*-

import MySQLdb
import time
import unittest


class StorageMysqlException(Exception):
    pass

class StorageMySql(object):
    def __init__(self):
        #TODO, in properties
        self.db = MySQLdb.connect("srv-umysqlm-02.moovapps.local",
                    "user_config","Bit6H2KXm9ii","moovapps_config" )
    def get_tenant_names(self,username):
        tenant_names=[]
        cursor = self.db.cursor()

        sql = "select t.tenantname as tenantname  \
	    from users u \
	    inner join users_tenants ut on u.id = ut.user_id \
	    inner join tenants t on ut.tenant_id  = t.id \
	    where u.username = '%s'" % (username)

        try:
            cursor.execute(sql)

            results = cursor.fetchall()

            for row in results:
                tenantname = row[0]
                tenant_names.append(tenantname)

        except MySQLdb.Error as e:
            print "Unexpected error:",e 
            raise e 
        finally:
            self.db.close()
            return tenant_names


class TestStorageMySql(unittest.TestCase):
    def setUp(self):
        pass
    def test0_get_tenant_names(self):
        storage_mysql = StorageMySql()
        tenant_names =  storage_mysql.get_tenant_names('rauburtin')
        print tenant_names

if __name__=='__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestStorageMySql)
    unittest.TextTestRunner(verbosity=2).run(suite)

