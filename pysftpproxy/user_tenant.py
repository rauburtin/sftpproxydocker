import os
import sys
import logging
import unittest
import time
import csv
from tenant import Tenant

class UserTenantException(Exception):
    pass

class UserTenant(object):
    def __init__(self, username):
        if username is None:
            raise UserTenantException("username is empty")
        self.username=username
        self.tenants=[]
    def add_tenant(self,tenant):
        if tenant is None:
            raise UserTenantException("tenant is None")
        self.tenants.append(tenant)
    @property
    def volumes(self):
        vols=[]
        for tenant in self.tenants:
            vols = vols + tenant.volumes
        return vols
    @property
    def volumes_binds(self):
        binds=[]
        for tenant in self.tenants:
            binds = binds + tenant.volumes_binds
        return binds

class UserTenantsException(Exception):
    pass

class UserTenants(object):
    def __init__(self):
        self.user_tenants_dict={}

    def add_user_tenant(self, username, tenantname):
        tenant=Tenant(tenantname)
        if not username in self.user_tenants_dict:
            user_tenant = UserTenant(username)
            user_tenant.add_tenant(tenant)
            self.user_tenants_dict[username] = user_tenant
        else:
            user_tenant = self.user_tenants_dict[username]
            user_tenant.add_tenant(tenant)

    def load_from_csv(self, file_csv):
        self.user_tenants_dict={}
        with open(file_csv, 'rb') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                username=row['username']
                tenantname=row['tenant']
                print username,tenantname
                self.add_user_tenant(username,tenantname)


class TestUserTenants(unittest.TestCase):
    def setUp(self):
        f=open("tenants.csv","wb")
        f.write("username,tenant\n")
        f.write("rauburtin,client1\n")
        f.write("rauburtin,client2\n")
        f.write("rauburtin,client3\n")
        f.write("rauburtin,client4\n")
        f.write("rauburtin,client5\n")
        f.write("pierre,client1\n")
        f.write("pierre,client2\n")

    def tearDown(self):
        os.unlink("tenants.csv")

    def test0_volumes(self):
        tenant1=Tenant("client1")
        tenant2=Tenant("client2")
        user_tenant=UserTenant("rauburtin")
        user_tenant.add_tenant(tenant1)
        user_tenant.add_tenant(tenant2)

        print user_tenant.volumes,user_tenant.volumes_binds

    def test1_user_tenants(self):
        user_tenants=UserTenants()
        user_tenants.load_from_csv("tenants.csv")
        for k,v in user_tenants.user_tenants_dict.items():
            print k, v.volumes, v.volumes_binds

if __name__=='__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestUserTenants)
    unittest.TextTestRunner(verbosity=2).run(suite)


