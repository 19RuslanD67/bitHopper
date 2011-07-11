#!/bin/python2.7
#License#
#bitHopper by Colin Rice is licensed under a Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported License.
#Based on a work at github.com.

import json
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
from twisted.internet import defer
from twisted.internet.defer import succeed, Deferred
from twisted.internet.task import LoopingCall
from twisted.internet.protocol import Protocol
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
def jsonrpc_lpcall(agent,server, url, update):
    try:
        global i
        request = json.dumps({'method':'getwork', 'params':[], 'id':i}, ensure_ascii = True)
        i = i +1
        
        header = {'Authorization':["Basic " +base64.b64encode(server['user']+ ":" + server['pass'])], 'User-Agent': ['bitHopper'],'Content-Type': ['application/json'] }
        d = agent.request('GET', "http://" + server['mine_address']+ url)
        d.addErrback(lambda x: defer.returnValue(None))
        body = yield d
        update(body)
    except Exception, e:
        print 'Caught, jsonrpc_lpcall'
        print e
        defer.returnValue(None)

@defer.inlineCallbacks
def jsonrpc_call(agent, server,data , set_lp):
    global i
    try:
        request = json.dumps({'method':'getwork', 'params':data, 'id':i}, ensure_ascii = True)
        i = i +1
        
        header = {'Authorization':["Basic " +base64.b64encode(server['user']+ ":" + server['pass'])], 'User-Agent': ['bitHopper'],'Content-Type': ['application/json'] }
        d = agent.request('POST', "http://" + server['mine_address'], Headers(header), StringProducer(request))
        response = yield d
        header = response.headers
        #Check for long polling header
        if set_lp(None, True):
            for k,v in header.getAllRawHeaders():
                if k.lower() == 'x-long-polling':
                    set_lp(v[0])
                    break

        finish = Deferred()
        response.deliverBody(WorkProtocol(finish))
        body = yield finish
    except Exception, e:
        print 'Caught, jsonrpc_call insides'
        print e
        defer.returnValue(None)

    try:
        message = json.loads(body)
        value =  message['result']
        defer.returnValue(value)
    except Exception, e:
        print "Error in json decoding, Server probably down"
        print body
        defer.returnValue(None)

@defer.inlineCallbacks
def jsonrpc_getwork(agent, server, data, j_id, request, new_server, set_lp):
    try:
        work = yield jsonrpc_call(agent, server,data,set_lp)
    except Exception, e:
            print 'caught, first response/writing'
            print e
            work = None
    i = 0
    while work == None and data != []:
        i += 1
        if i > 3:
            new_server(server)
        try:
            work = yield jsonrpc_call(agent, server,data,set_lp)
            time.sleep(0.1)
        except Exception, e:
            print 'caught, inner jsonrpc_call loop'
            print e
            continue

    try:
        if work != None:
            response = json.dumps({"result":work,'error':None,'id':j_id})
        else:
            new_server(server)
            response = json.dumps({"result":None,'error':{"message':'Server isn't responding"},'id':j_id})
        request.write(response)
        request.finish()
    except Exception, e:
            print 'caught, Final response/writing'
            print e
