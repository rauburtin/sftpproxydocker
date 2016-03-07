"""Proxy SFTP client. Forward each request to another SFTP server."""

import sys 
import os

from twisted.python import log
import logging

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet import defer

from twisted.conch.ssh.common import NS
from twisted.conch.scripts.cftp import ClientOptions
from twisted.conch.client.connect import connect
#from twisted.conch.client.default import SSHUserAuthClient, verifyHostKey
from twisted.conch.client.default import SSHUserAuthClient
from twisted.conch.ssh.connection import SSHConnection
from twisted.conch.ssh.channel import SSHChannel
from twisted.conch.ssh.filetransfer import FXF_WRITE, FXF_CREAT, \
    FXF_TRUNC, FileTransferClient

def verifyHostKey(transport, host, pubKey, fingerprint):
    return defer.succeed(1)

class SFTPSession(SSHChannel):
    name = 'session'

    def channelOpen(self, whatever):
        d = self.conn.sendRequest(
            self, 'subsystem', NS('sftp'), wantReply=True)
        d.addCallbacks(self._cbSFTP)


    def _cbSFTP(self, result):
        # great explanation here http://stackoverflow.com/questions/5195427/twisted-conch-filetransfer
        client = FileTransferClient()
        client.makeConnection(self)
        self.dataReceived = client.dataReceived
        #here we fire the _sftp Deferred with the reference to the client
        self.conn._sftp.callback(client)
        self.conn.transport.transport.setTcpNoDelay(1)

    def closed(self):
        log.msg("channel Closed", self.catData, logLevel=logging.DEBUG)


class SFTPConnection(SSHConnection):
    def serviceStarted(self):
        self.openChannel(SFTPSession())
    def serviceStopped(self):
        log.msg("Service Stopped", logLevel=logging.DEBUG)


class SFTPServerProxyClient(object): 
    def __init__(self, remote=None,
                 key=None, port=None,
                 user=None, ssh_config_path=None,
                 ssh_agent=False, known_hosts_path=None):

        self.host = 'localhost'
        if remote:
            self.host = remote

        self.port = 22
        if port:
            self.port = port

        self.user = os.environ.get("SFTPPROXY_CLIENT_USER",'rauburtin')
        if user:
            self.user = user

        self.dcli = self.connect_sftp()

        #called when the client is defined, we have to set the member client of this class to hold a direct pointer
        #we can't use only a deferred because a deferred can only be called once
        self.dcli.addCallback(self.set_client)	
        self.dcli.addErrback(log.err, "Problem with SFTP transfer")

    def set_client(self,client):
        log.msg("Setting client", logLevel=logging.DEBUG)
        self.client = client

    def connect_sftp(self):
        conn = SFTPConnection()
        self.conn = conn
        conn._sftp = Deferred()
        options = ClientOptions()
        options['host'] = self.host
        options['port'] = self.port

        log.msg("self.host", self.host, logLevel=logging.DEBUG)
        log.msg("self.port", self.port, logLevel=logging.DEBUG)
        log.msg("self.user", self.user, logLevel=logging.DEBUG)

        self.auth = SSHUserAuthClient(self.user, options, conn)
        connect(self.host, self.port, options, verifyHostKey, self.auth)
        self._sftp = conn._sftp
        return self._sftp

