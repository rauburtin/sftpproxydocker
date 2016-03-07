#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
import logging
import unittest
import time

ROOT_VOLUMES="/home/rauburtin/data"
MOUNT_VOLUMES="/mnt"

class TenantException(Exception):
    pass
class Tenant:
    def __init__(self, name):
        if name is None:
            raise TenantException("name is empty")
        self.name = name
    @property
    def volumes(self):
        vols = [os.path.join(MOUNT_VOLUMES,self.name,'prod'),
                os.path.join(MOUNT_VOLUMES,self.name,'preprod')]
        return vols
    @property
    def volumes_binds(self):
        binds = [os.path.join(ROOT_VOLUMES,self.name,'prod')+ ':'+\
                os.path.join(MOUNT_VOLUMES,self.name,'prod')+':ro',
                os.path.join(ROOT_VOLUMES,self.name,'preprod')+ ':'+\
                os.path.join(MOUNT_VOLUMES,self.name,'preprod')]
        return binds

class TestTenant(unittest.TestCase):
    def setUp(self):
        pass
    def test0_volumes(self):
        tenant=Tenant("client1")
        print tenant.volumes_binds, tenant.volumes

if __name__=='__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestTenant)
    unittest.TextTestRunner(verbosity=2).run(suite)

