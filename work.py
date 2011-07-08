#!/bin/python2.7
#License#
#bitHopper by Colin Rice is licensed under a Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported License.
#Based on a work at github.com.

import json
import time
from jsonrpc import ServiceProxy
import socket
import os
import base64
import exceptions

from zope.interface import implements

from twisted.web import server, resource
from twisted.web.client import getPage, Agent
from twisted.web.iweb import IBodyProducer
from twisted.web.http_headers import Headers
from twisted.internet import reactor, threads, defer
from twisted.internet.defer import succeed, Deferred
from twisted.internet.task import LoopingCall
from twisted.internet.protocol import Protocol
from twisted.python import log

i = 1

class StringProducer(object):
    implements(IBodyProducer)

    def __init__(self, body):
        self.body = body
        self.length = len(body)
    def startProducing(self, consumer):
        consumer.write(self.body)
        return succeed(None)

    def pauseProducing(self):
        pass

    def stopProducing(self):
        pass

class WorkProtocol(Protocol):

    def __init__(self, finished):
        self.data = ""
        self.finished = finished
    
    def dataReceived(self, data):
        self.data += data

    def connectionLost(self, reason):
        self.finished.callback(self.data)

@defer.inlineCallbacks
def jsonrpc_call(agent, server,data = []):
    global i
    request = json.dumps({'method':'getwork', 'params':data, 'id':i}, ensure_ascii = True)
    i = i +1
    
    header = {'Authorization':["Basic " +base64.b64encode(server['user']+ ":" + server['pass'])], 'User-Agent': ['bitHopper'],'Content-Type': ['application/json'] }
    d = agent.request('POST', "http://" + server['mine_address'], Headers(header), StringProducer(request))
    response = yield d
    finish = Deferred()
    response.deliverBody(WorkProtocol(finish))
    body = yield finish
    try:
        message = json.loads(body)
        value =  message['result']
        defer.returnValue(value)
    except exceptions.ValueError, e:
        log.err(e)
        defer.returnValue(None)

@defer.inlineCallbacks
def jsonrpc_getwork(agent, server, data, j_id, request, new_server):
    work = None
    i = 0
    while work == None:
        i += 1
        if i > 10:
            new_server(server)
        work = yield jsonrpc_call(agent, server,data)

    response = json.dumps({"result":work,'error':None,'id':j_id})

    request.write(response)
    request.finish()
