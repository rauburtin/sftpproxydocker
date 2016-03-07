#!/usr/bin/env python
"""
The SFTP server that acts as a reverse proxy
"""
import base64, os, fcntl, tty, struct

from twisted.enterprise import adbapi

from twisted.cred import portal, checkers, credentials, error
from twisted.conch import error, avatar
from twisted.conch.unix import SSHSessionForUnixConchUser,UnixConchUser, SFTPServerForUnixConchUser, UnixSFTPDirectory, UnixSFTPFile
from twisted.conch.checkers import SSHPublicKeyDatabase
from twisted.conch.ssh import factory, userauth, connection, keys, session
from twisted.internet import reactor, protocol, defer, task
from twisted.internet.defer import inlineCallbacks
from twisted.python import log, logfile
import logging
from zope.interface import implements
from twisted.python import components, failure
from twisted.conch.ssh import session, forwarding, filetransfer
from sshproxydocker.client import SFTPServerProxyClient
from twisted.internet.protocol import Protocol, ReconnectingClientFactory
from twisted.conch.ls import lsLine
from sshproxydocker.levfilelogger import LevelFileLogObserver
from sshproxydocker.storageredis import StorageRedis
from sshproxydocker.auth_backends import ActiveDirectoryBackend

from sshproxydocker.tenant import Tenant,MOUNT_VOLUMES
from sshproxydocker.user_tenant import UserTenant
from sshproxydocker.container import SshdContainerUserTenant,DOCKER_HOST
from docker import Client
import time

import sys

publicKeyPath  = os.environ.get("SFTPPROXY_PUBLICKEY_PATH",
    "/home/rauburtin/.ssh/id_rsa.pub")
publicKey = open(publicKeyPath,"r").read()
if publicKey.endswith("\n"):
    publicKey = publicKey[:-1]

privateKeyPath = os.environ.get("SFTPPROXY_PRIVATEKEY_PATH",
    "/home/rauburtin/.ssh/id_rsa")
privateKey = open(privateKeyPath,"r").read()
if privateKey.endswith("\n"):
    privateKey = privateKey[:-1]


class ActiveDirectoryCredentialsChecker(object):
    implements(checkers.ICredentialsChecker)
    credentialInterfaces=[credentials.IUsernamePassword,]

    def requestAvatarId(self,credentials):
        try:
            username=credentials.username
            password=credentials.password

            log.msg("Client username %s password %s " % (username,password), logLevel=logging.DEBUG)
            auth =  ActiveDirectoryBackend()
            user = auth.authenticate(username,password)
            if not user is None:
                return defer.succeed(username)
            else:
                return defer.fail(error.UnauthorizedLogin(
                "invalid password or group for username: %s" % (username)))
        except:
            raise credError.UnauthorizedLogin,"Cannot bind/access LDAP"

class PublicKeyCredentialsChecker:
    implements(checkers.ICredentialsChecker)
    #Only chek publick keys used by client
    credentialInterfaces = (credentials.ISSHPrivateKey,)

    def requestAvatarId(self, credentials):
        # check http://wiki.velannes.com/doku.php?id=python:programmes:twisted_ssh_server
        publickey = base64.b64encode(credentials.blob)
        log.msg("Client publickey:%s" % (publickey), logLevel=logging.DEBUG)
        log.msg("Client username %s" % (credentials.username), logLevel=logging.DEBUG)

        sredis = StorageRedis()
        username = sredis.get_username(publickey)

        log.msg("username from redis",username, logLevel=logging.DEBUG)

        if username == credentials.username:
            return defer.succeed(credentials.username)
        else:
            return defer.fail(error.UnauthorizedLogin(
                "invalid pubkey for username: %s" % (credentials.username)))

class ProxySSHUser(avatar.ConchUser):

    def __init__(self, username):
        avatar.ConchUser.__init__(self)
        self.username = username
        self.otherGroups = []

        self.channelLookup.update({'session':session.SSHSession})
        self.subsystemLookup['sftp'] = filetransfer.FileTransferServer
        #here we can create the client
        #need to pass the remote ssh server ip and port
        log.msg("Start SFTPServerProxyClient", logLevel=logging.DEBUG)
        sredis = StorageRedis()
        userinfo = sredis.get_userinfo(username)

        log.msg("userinfo from redis",userinfo, logLevel=logging.DEBUG)


        #START HACK
        tenant1=Tenant("client1")
        tenant2=Tenant("client2")
        #tenant3=Tenant("client3")
        sshd_container_user_tenant=SshdContainerUserTenant(username)
        sshd_container_user_tenant.add_tenant(tenant1)
        sshd_container_user_tenant.add_tenant(tenant2)
        #sshd_container_user_tenant.add_tenant(tenant3)

        print sshd_container_user_tenant.volumes,sshd_container_user_tenant.volumes_binds
        sshd_container_user_tenant.start()
        sshd_container_user_tenant.wait()

        print 'logs',sshd_container_user_tenant.logs
        print sshd_container_user_tenant.ports
        ssh_port=sshd_container_user_tenant.exposed_port
        self.proxyclient = SFTPServerProxyClient(
                remote=DOCKER_HOST,
                port=int(ssh_port))
        #END HACK

        #self.proxyclient = SFTPServerProxyClient(
        #        remote=userinfo['remote'],
        #        port=int(userinfo['port']))


    def getUserGroupId(self):
        userid = int(os.environ.get("SFTPPROXY_USERID",1000))
        groupid = int(os.environ.get("SFTPPROXY_GROUPID",1000))
        return userid,groupid

    def getHomeDir(self):
        return os.environ.get("SFTPPROXY_HOME",'/home/rauburtin')

    def getOtherGroups(self):
        return self.otherGroups

    def _runAsUser(self, f, *args, **kw):
        euid = os.geteuid()
        egid = os.getegid()
        groups = os.getgroups()
        uid, gid = self.getUserGroupId()
        os.setegid(0)
        os.seteuid(0)
        os.setgroups(self.getOtherGroups())
        os.setegid(gid)
        os.seteuid(uid)
        try:
            f = iter(f)
        except TypeError:
            f = [(f, args, kw)]
        try:
            for i in f:
                func = i[0]
                args = len(i) > 1 and i[1] or ()
                kw = len(i) > 2 and i[2] or {}
                r = func(*args, **kw)
        finally:
            os.setegid(0)
            os.seteuid(0)
            os.setgroups(groups)
            os.setegid(egid)
            os.seteuid(euid)
        return r

    def logout(self):
        # Remove all listeners.
        log.msg("logout", logLevel=logging.DEBUG )
        for listener in self.listeners.itervalues():
            self._runAsUser(listener.stopListening)
        log.msg(
            'avatar %s logging out (%i)'
            % (self.username, len(self.listeners)), logLevel=logging.DEBUG)

class ProxySSHRealm:
    implements(portal.IRealm)

    def requestAvatar(self, avatarId, mind, *interfaces):
        return interfaces[0], ProxySSHUser(avatarId), lambda: None

class ProxySFTPSession(SFTPServerForUnixConchUser):

    def gotVersion(self, otherVersion, extData):
        if not hasattr(self.avatar.proxyclient, "client"):
            return {}
        else:
            return {}
            #log.msg("gitVersion otherVersion:%s extData:%s" % (otherVersion, extData), logLevel=logging.DEBUG)
            #return self.avatar.proxyclient.client.gotVersion(otherVersion, extData)


    def openFile(self, filename, flags, attrs):
        log.msg("openFile filename:%s flags:%s attrs:%s" % (filename, flags, attrs), logLevel=logging.DEBUG)
        return self.avatar.proxyclient.client.openFile(filename, flags, attrs)


    def removeFile(self, filename):
        log.msg("removeFile filename:%s" % (filename), logLevel=logging.DEBUG)
        return self.avatar.proxyclient.client.removeFile(filename)


    def renameFile(self, oldpath, newpath):
        log.msg("renameFile oldpath:%s newpath:%s" % (oldpath, newpath), logLevel=logging.DEBUG)
        return self.avatar.proxyclient.client.renameFile(oldpath, newpath)


    def makeDirectory(self, path, attrs):
        log.msg("makeDirectory path:%s attrs:%s" % (path, attrs), logLevel=logging.DEBUG)
        return self.avatar.proxyclient.client.makeDirectory(path, attrs)

    def removeDirectory(self, path):
        log.msg("removeDirectory path:%s" % (path), logLevel=logging.DEBUG)
        return self.avatar.proxyclient.client.removeDirectory(path)


    def openDirectory(self, path):
        log.msg("openDirectory path:%s" % (path), logLevel=logging.DEBUG)
        files = []
        def _getFiles(openDir):
            def append(f):
                files.append(f)
                return openDir
            d = defer.maybeDeferred(openDir.next)
            d.addCallback(append)
            d.addCallback(_getFiles)
            d.addErrback(_close, openDir)
            return d

        def _close(_, openDir):
            d = openDir.close()
            return d
        def _setFiles(d,proxy):
            proxy.set_files(files)
            return d
        def _openDirectory(_,path):
           d = self.avatar.proxyclient.client.openDirectory(path)
           return d


        #not so bad, with _openDirectory(path)
        #d =  task.deferLater(reactor,1,_openDirectory,path)
        d = self.avatar.proxyclient.dcli
        d.addCallback(_openDirectory,path)
        d.addCallback(_getFiles)
        d.addCallback(ProxySFTPDirectory,files)

        return d

    def getAttrs(self, path, followLinks):
        log.msg("getAttrs path:%s followLinks:%s" % (path, followLinks), logLevel=logging.DEBUG)
        return self.avatar.proxyclient.client.getAttrs(path, followLinks)


    def setAttrs(self, path, attrs):
        log.msg("setAttrs path:%s attrs:%s" % (path, attrs), logLevel=logging.DEBUG)
        return self.avatar.proxyclient.client.setAttrs(path, attrs)


    def readLink(self, path):
        log.msg("readLink path:%s" % (path), logLevel=logging.DEBUG)
        return self.avatar.proxyclient.client.readLink(path)


    def makeLink(self, linkPath, targetPath):
        log.msg("makeLink linkPath:%s targetPath:%s" % (linkPath, targetPath), logLevel=logging.DEBUG)
        return self.avatar.proxyclient.client.makeLink(linkPath, targetPath)


    def realPath(self, path):
        if not hasattr(self.avatar.proxyclient, "client"):
            return os.path.realpath(self._absPath(path))
        else:
            log.msg("realPath path:%s" % (path), logLevel=logging.DEBUG)
            return self.avatar.proxyclient.client.realPath(path)


    def extendedRequest(self, extName, extData):
        raise NotImplementedError

class ProxySFTPDirectory:
    def __init__(self,d,files):
        self.files=files
    def set_files(self,files):
        self.files=files
    def __iter__(self):
        return self
    def next(self):
        try:
            f = self.files.pop(0)
            return (f[0],f[1],f[2])
        except IndexError:
            raise StopIteration
    def close(self):
        pass


class ProxySSHFactory(factory.SSHFactory):

    publicKeys  = { 'ssh-rsa': keys.Key.fromString(data=publicKey)   }
    privateKeys = { 'ssh-rsa': keys.Key.fromString(data=privateKey) }
    services = {
        'ssh-userauth': userauth.SSHUserAuthServer,
        'ssh-connection': connection.SSHConnection
    }

class ProxySFTPServer(object):
    def __init__(self, filelog=None, dirlog="../log/", rotateLengthMB=1,
            maxRotatedFiles=100):
        f = sys.stdout
        if filelog:
            if not os.path.isdir(dirlog):
                os.makedirs(dirlog)
            f  = logfile.LogFile(filelog, dirlog,
                    rotateLength=rotateLengthMB*1000000,
                    maxRotatedFiles=maxRotatedFiles)

        self.logger = LevelFileLogObserver(f, logging.DEBUG)

    def run(self):

        global portal

        #Start Logging
        log.addObserver(self.logger.emit)
        log.msg("Logging started", logLevel=logging.DEBUG)

        portal = portal.Portal(ProxySSHRealm())

        components.registerAdapter(ProxySFTPSession, ProxySSHUser, filetransfer.ISFTPServer)
        portal.registerChecker(PublicKeyCredentialsChecker())
        portal.registerChecker(ActiveDirectoryCredentialsChecker())
        ProxySSHFactory.portal = portal

        reactor.listenTCP(int(os.environ.get("SFTPPROXY_PORT",5022)), ProxySSHFactory())
        reactor.run()

if __name__ == '__main__':
    proxyserver = ProxySFTPServer()
    proxyserver.run()
