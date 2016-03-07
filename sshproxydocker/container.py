import unittest
from tenant import Tenant,MOUNT_VOLUMES
from user_tenant import UserTenant
from docker import Client
import time

DOCKER_HOST='tst-usambot-01.moovapps.local'
DOCKER_URL='tcp://'+DOCKER_HOST+':4243'

class ContainerUserTenant(UserTenant):
    def __init__(self,username):
        super(ContainerUserTenant,self).__init__(username)

    def exists(self,image=None,name=None,extra_volumes_binds=[]):
        self.cli = Client(base_url=DOCKER_URL)
        containers=self.cli.containers(all=True)
        for container in containers:
            if image==container['Image']:
                if '/'+name in container['Names']:
                    binds = self.cli.inspect_container(container['Id'])['HostConfig']['Binds']
                    volumes_binds = self.volumes_binds + extra_volumes_binds
                    binds.sort()
                    volumes_binds = [unicode(x) for x in volumes_binds]
                    volumes_binds.sort()

                    if binds == volumes_binds:
                        return container['Id'], True, ('Up' in container['Status'])
                    else:
                        return container['Id'], False, ('Up' in container['Status'])

        return None,None,None

    def start(self, image='alpine', detach=False, 
            command='ls -R %s' % (MOUNT_VOLUMES),
            ports=[],
            port_bindings={},
            extra_volumes=[],
            extra_volumes_binds=[],
            name=None):

        self.cli = Client(base_url=DOCKER_URL)

        (container_id,container_same_vols,container_up) = self.exists(
                image=image, name=name,
                extra_volumes_binds = extra_volumes_binds)

        if not container_id is None:
            if container_same_vols and container_up:
                self.container_id  = container_id
                return
            else:
                self.remove_by_id(container_id)

        self.container_id = self.cli.create_container(image=image,
                detach=detach,
                command=command, 
                ports=ports,
                volumes=extra_volumes+self.volumes,
                host_config=self.cli.create_host_config(binds =
                    extra_volumes_binds + self.volumes_binds,
                    port_bindings=port_bindings),
                name=name
                )
        self.cli.start(self.container_id)

    @property
    def logs(self):
        return self.cli.logs(self.container_id)

    def wait(self,timeout=10,search_string=None):
        t1=time.time()
        while (time.time()-t1) < timeout:
            if search_string in self.logs:
                break

    def remove(self):
        return self.cli.remove_container(self.container_id,v=True,force=True)

    def remove_by_id(self,container_id):
        return self.cli.remove_container(container_id,v=True,force=True)

    @property
    def ports(self):
        return self.cli.inspect_container(self.container_id)['NetworkSettings']['Ports']

class SshdContainerUserTenant(ContainerUserTenant):
    sshd_image='mini_sshd'
    def __init__(self,username):
        super(SshdContainerUserTenant,self).__init__(username)
        self.name = '%s_%s' % (self.sshd_image,self.username)

    def start(self):
        super(SshdContainerUserTenant,self).start(image = self.sshd_image,
                detach=True,
                command=None,
                ports=[22],
                port_bindings={22:None},
                extra_volumes=['/secrets/id_rsa.pub'],
                extra_volumes_binds=['/secrets/id_rsa.pub:/root/.ssh/authorized_keys:ro'],
                name=self.name
                )
        # name='%s_%s' % (self.sshd_image,self.username) 

    def wait(self,timeout=10):
        super(SshdContainerUserTenant,self).wait(timeout=timeout,search_string='/etc/ssh/sshd_config')

    @property
    def exposed_port(self):
        return super(SshdContainerUserTenant,self).ports['22/tcp'][0]['HostPort']

class TestSshdContainerUserTenant(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test0_volumes(self):
        return
        tenant1=Tenant("client1")
        tenant2=Tenant("client2")
        container_user_tenant=ContainerUserTenant("rauburtin")
        container_user_tenant.add_tenant(tenant1)
        container_user_tenant.add_tenant(tenant2)

        print container_user_tenant.volumes,container_user_tenant.volumes_binds
        container_user_tenant.start()
        print container_user_tenant.logs
        container_user_tenant.remove()
    def test0_sshcont(self):
        #return
        tenant1=Tenant("client1")
        tenant2=Tenant("client2")
        #tenant3=Tenant("client3")
        sshd_container_user_tenant=SshdContainerUserTenant("rauburtin")
        sshd_container_user_tenant.add_tenant(tenant1)
        sshd_container_user_tenant.add_tenant(tenant2)
        #sshd_container_user_tenant.add_tenant(tenant3)

        print sshd_container_user_tenant.volumes,sshd_container_user_tenant.volumes_binds
        sshd_container_user_tenant.start()
        sshd_container_user_tenant.wait()

        print 'logs',sshd_container_user_tenant.logs
        print sshd_container_user_tenant.ports
        print sshd_container_user_tenant.exposed_port
        #sshd_container_user_tenant.remove()


if __name__=='__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSshdContainerUserTenant)
    unittest.TextTestRunner(verbosity=2).run(suite)




