'''
Generic message-based protocol used by Bitcoin and P2Pool for P2P communication
'''

import hashlib
import struct

from twisted.internet import protocol
from twisted.python import log

import p2pool
from p2pool.util import datachunker

class TooLong(Exception):
    pass

class Protocol(protocol.Protocol):
    def __init__(self, message_prefix, max_payload_length):
        self._message_prefix = message_prefix
        self._max_payload_length = max_payload_length
        self.dataReceived = datachunker.DataChunker(self.dataReceiver())
    
    def dataReceiver(self):
        while True:
            start = ''
            while start != self._message_prefix:
                start = (start + (yield 1))[-len(self._message_prefix):]
            
            command = (yield 12).rstrip('\0')
            length, = struct.unpack('<I', (yield 4))
            if length > self._max_payload_length:
                print 'length too large'
                continue
            checksum = yield 4
            payload = yield length
            
            if hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4] != checksum:
                print 'invalid hash for', self.transport.getPeer().host, repr(command), length, checksum.encode('hex'), hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4].encode('hex'), payload.encode('hex')
                continue
            
            type_ = getattr(self, 'message_' + command, None)
            if type_ is None:
                if p2pool.DEBUG:
                    print 'no type for', repr(command)
                continue
            
            try:
                self.packetReceived(command, type_.unpack(payload))
            except:
                print 'RECV', command, payload[:100].encode('hex') + ('...' if len(payload) > 100 else '')
                log.err(None, 'Error handling message: (see RECV line)')
                self.badPeerHappened()
    
    def packetReceived(self, command, payload2):
        handler = getattr(self, 'handle_' + command, None)
        if handler is None:
            if p2pool.DEBUG:
                print 'no handler for', repr(command)
            return
        
        handler(**payload2)
    
    def badPeerHappened(self):
        self.transport.loseConnection()
    
    def sendPacket(self, command, payload2):
        if len(command) >= 12:
            raise ValueError('command too long')
        type_ = getattr(self, 'message_' + command, None)
        if type_ is None:
            raise ValueError('invalid command')
        #print 'SEND', command, repr(payload2)[:500]
        payload = type_.pack(payload2)
        if len(payload) > self._max_payload_length:
            raise TooLong('payload too long')
        self.transport.write(self._message_prefix + struct.pack('<12sI', command, len(payload)) + hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4] + payload)
    
    def __getattr__(self, attr):
        prefix = 'send_'
        if attr.startswith(prefix):
            command = attr[len(prefix):]
            return lambda **payload2: self.sendPacket(command, payload2)
        #return protocol.Protocol.__getattr__(self, attr)
        raise AttributeError(attr)
