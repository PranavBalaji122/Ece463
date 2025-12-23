#
import _thread
import sys
import queue
import time
import threading

class Link:
    """Link class implements the link between two routers/clients.
       Handles sending and receiving packets using threadsafe queues.
    """

    def __init__(self, e1, e2, cost, MSS):
        """Create queues. e1 & e2 are addresses of the 2 endpoints of the link"""
        self.q12 = queue.Queue()
        self.q21 = queue.Queue()
        self.cost = cost
        self.latency = cost
        self.MSS = MSS
        self.e1 = e1
        self.e2 = e2


    def send(self, packet, src):
        """Sends 'packet' from 'src' on this link.
           Checks packet payload is a string of size <= MSS.
           'src' must be equal to self.e1 or self.e2.
        """
        if packet.payload:
            assert(isinstance((packet.payload), str) and (len(packet.payload)<= self.MSS)), "Packet payload must be a string of length <= " + self.MSS + " bytes"
        if src == self.e1:
            packet.time = time.time()
            self.q12.put(packet)
        elif src == self.e2:
            packet.time = time.time()
            self.q21.put(packet)


    def recv(self, dst, timeout=None):
        """Checks whether a packet is ready to be received by 'dst' on this link.
           'dst' must be equal to self.e1 or self.e2.
           If packet is ready, returns the packet, else returns 'None'.
        """
        if dst == self.e1:
            if not self.q21.empty():
                currTime = time.time()
                enqeueTime = self.q21.queue[0].time
                if currTime - enqeueTime >= self.latency:
                    packet = self.q21.get_nowait()
                    return packet
                else:
                    return None
            else:
                return None
        elif dst == self.e2:
            if not self.q12.empty():
                currTime = time.time()
                enqeueTime = self.q12.queue[0].time
                if currTime - enqeueTime >= self.latency:
                    packet = self.q12.get_nowait()
                    return packet
                else:
                    return None
            else:
                return None


