# tracks accuracy of block predictions as noted in lp.blocks['_owner']
# required pident plugin to work
import time
import eventlet
import traceback

from eventlet.green import time, threading
from peak.util import plugins

class BlockAccuracy:
    def __init__(self, bitHopper):
        self.bitHopper = bitHopper
        self.blocks = {}
        #self.announce_threshold = 20
        self.log_dbg('Registering hooks')
        # register plugin hooks        
        hook = plugins.Hook('plugins.poolblocks.verified')
        hook.register(self.block_verified)
        self.lastreport = time.time()

    def log_msg(self, msg):
        self.bitHopper.log_msg(msg, cat='block-accuracy')
    
    def log_dbg(self, msg):
        self.bitHopper.log_dbg(msg, cat='block-accuracy')
        
    def log_trace(self, msg):
        self.bitHopper.log_trace(msg, cat='block-accuracy')
        
    def block_verified(self, blockNumber, blockHash, pool):
        block = blockHash
        self.log_trace('block_verified recv() ' + str(pool) + ' ' + str(block))
        if block != None and pool != None:
            self.log_dbg('Adding block owner ' + str(pool) + ' for ' + str(block))
            self.blocks[block] = {}
            self.blocks[block]['verified'] = pool
        else:
            self.log_msg('Bad notify: ' + str(block) + '/' + str(pool))
        
        if time.time() > self.lastreport + 60:
            self.lastreport = time.time()
            self.report()
            
    def report(self):
        self.log_trace('report()')
        pools = {}
        for pool in self.bitHopper.pool.get_servers():
            pools[pool] = {}
            pools[pool]['hit'] = 0
            pools[pool]['miss'] = 0
            pools[pool]['total'] = 0
        
        # for each block see if we have verification
        try:
            for block in self.bitHopper.lp.blocks:
                self.log_trace('block: ' + str(block))
                lp_owner = str(self.bitHopper.lp.blocks[block]['_owner'])
                print " - lp_owner: " + str(lp_owner)
                verified_owner = None
                if block in self.blocks:
                    verified_owner = str(self.blocks[block]['verified'])
                    self.log_trace('verified owner: ' + str(verified_owner) + ' for ' + str(block))
                if lp_owner == verified_owner:
                    self.log_trace('hit ' + str(lp_owner) + ' for block ' + str(block) )
                    pools[lp_owner]['hit'] += 1                    
                    pools[lp_owner]['total'] += 1
                elif verified_owner != None:
                    self.log_trace('mispredict ' + str(lp_owner) + ' was ' + str(verified_owner) + ' for block ' + str(block) )
                    pools[lp_owner]['miss'] += 1
                    pools[lp_owner]['total'] += 1
                    pools[verified_owner]['total'] += 1
                else:
                    self.log_trace('no verified owner for ' + str(block))
                    
            for pool in pools:
                self.log_trace('/pool/' + str(pool))
                total = pools[pool]['total']
                hit = pools[pool]['hit']
                miss = pools[pool]['miss']
                if total == 0:
                    pct = float(0)
                else:
                    pct = (float(hit) / total) * 100
                msg = '%(pool)16s %(hit)4d hits / %(miss)4d misses / %(total)6d / %(hit_percent)2.1f%% hit' % \
                      {"pool": pool, "hit":hit, "miss":miss, "total":total, "hit_percent":pct}
                self.log_msg(msg)
                
        except Exception, e:
            if self.bitHopper.options.debug:
                traceback.print_exc()
    
    #def lp_announce(self, lpobj, body, server, block):
    #    self.log_msg(server + ': ' + block)
    #    if block not in self.blocks:
    #        self.blocks[block] = {}
    #        self.blocks[block]['verified'] = None
    #    if 'initial_timestamp' in self.blocks:
    #        now = time.time()
    #        if now - self.blocks['initial_timestamp'] < self.announce_threshold:
    #            # assume same block
    #            self.blocks[block]['initial'] = server
    #        else:
    #            self.log_dbg('Rejected ' + server + ' for ' + block + ' due to time')
    #    else:
    #        # first block seen
    #        self.blocks[block]['initial_timestamp'] = time.time()
    #        self.blocks[block]['initial'] = server
    #        