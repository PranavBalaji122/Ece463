import sys
from collections import defaultdict
from router import Router
from packet import Packet
from json import dumps, loads

class DVrouter(Router):
    """Distance vector routing and forwarding implementation"""

    def __init__(self, addr, heartbeatTime, infinity):
        Router.__init__(self, addr, heartbeatTime) 
        self.infinity = int(infinity)
        """add your own class fields and initialization code here"""
        self.routingTable = {} 
        self.Nebhr2Port = {}
        self.port2nbr = {}
        self.nbrCost = {}
        self.nbrVectors = {}  
        self.routingTable[self.addr] = (0, self.addr)


    def send_vector_to(self, nbr):
        """Send our DV to one neighbor with poison-reverse."""
        port = self.Nebhr2Port.get(nbr)
        if port is None:
            return

        vec = {}
        for dest, (cost, nextHop) in self.routingTable.items():
            adv_cost = self.infinity if nextHop == nbr else cost  

            if adv_cost > self.infinity:
                adv_cost = self.infinity
            vec[dest] = adv_cost

        vec[self.addr] = 0  
        pkt = Packet(Packet.CONTROL, self.addr, nbr, dumps(vec))
        self.send(port, pkt)


    def handlePacket(self, port, packet):
        """Process incoming packet.
           This method is called whenever router receives a packet (CONTROL or DATA).

           Parameters:
           port : the router port on which the packet was received
           packet : the received packet
        """

        if packet.isControl():
            try:
                vec = loads(packet.content)
            except:
                return  

            src = packet.srcAddr  
            cost_to_src = self.nbrCost.get(src)
            if cost_to_src is None:
                return  
            self.nbrVectors[src] = vec

            helper = False
            for dest, adv_cost in vec.items():
                if dest == self.addr:
                    continue
                new_cost = min(self.infinity, cost_to_src + adv_cost)

                curr = self.routingTable.get(dest)  
                if (curr is None) or (new_cost < curr[0]) or (curr[1] == src and new_cost != curr[0]):
                    self.routingTable[dest] = (new_cost, src)
                    helper = True
                    
            if helper:
                for n in self.Nebhr2Port.keys():
                    self.send_vector_to(n)

        elif packet.isData():  
            packetDst = packet.dstAddr
            data = self.routingTable.get(packetDst)
            if data is None:
                return

            if data[0] >= self.infinity:
                return
            
            outPort = self.Nebhr2Port.get(data[1])
            if outPort is None:
                return
            self.send(outPort, packet)
        else:
            pass


    def handleNewLink(self, port, endpoint, cost):
        """This method is called whenever a new link (including each of the initial links in the json file)
           is added to a router port, or an existing link cost is updated.
           The 'links' data structure in router.py has already been updated with this change.
           Implement any routing/forwarding action that you might want to take under such a scenario.

           Parameters:
           port : router port of the new link / the existing link whose cost has been updated
           endpoint : the node at the other end of the new link / the exisitng link whose cost has been updated
           cost : cost of the new link / updated cost of the exisitng link
        """

        self.port2nbr[port] = endpoint
        self.nbrCost[endpoint] = int(cost)
        self.Nebhr2Port[endpoint] = port
        direct = (int(cost), endpoint)
        prev = self.routingTable.get(endpoint)

        if (prev is None) or (direct[0] < prev[0]) or (prev[1] == endpoint and direct[0] != prev[0]):
            self.routingTable[endpoint] = direct

        self.send_vector_to(endpoint)


    def handleRemoveLink(self, port, endpoint):
        """This method is called whenever an existing link is removed from the router port.
           The 'links' data structure in router.py has already been updated with this change.
           Implement any routing/forwarding action that you might want to take under such a scenario.

           Parameters:
           port : router port from which the link has been removed
           endpoint : the node at the other end of the removed link
        """
        self.port2nbr.pop(port, None)
        self.Nebhr2Port.pop(endpoint, None)
        self.nbrCost.pop(endpoint, None)
        self.nbrVectors.pop(endpoint, None)

        helper = False
        for dest, (c, nh) in list(self.routingTable.items()):
            if nh == endpoint:
                if c != self.infinity:
                    self.routingTable[dest] = (self.infinity, nh)
                    helper = True

        for nbr, vec in self.nbrVectors.items():
            cost_to_nbr = self.nbrCost.get(nbr)
            if cost_to_nbr is None:
                continue
                
            for dest, adv_cost in vec.items():
                if dest == self.addr:
                    continue
                    
                new_cost = min(self.infinity, cost_to_nbr + adv_cost)
                curr = self.routingTable.get(dest)
                
                if curr is None or curr[0] >= self.infinity or new_cost < curr[0]:
                    if self.routingTable.get(dest) != (new_cost, nbr):
                        self.routingTable[dest] = (new_cost, nbr)
                        helper = True
        if helper:
            for n in self.Nebhr2Port.keys():
                self.send_vector_to(n)


    def handlePeriodicOps(self):
        """Handle periodic operations. This method is called every 'heartbeatTime'.
           The value of 'heartbeatTime' is specified in the json file.
        """
        for nbr in list(self.Nebhr2Port.keys()):
            self.send_vector_to(nbr)