#
import _thread
import sys
import queue
import time
import threading

class Link:
    """Link class implements the link between two routers/clients.
       Handles sending and receiving packets using threadsafe queues
    """

    def __init__(self, e1, e2, l, latency):
        """Create queues. e1 & e2 are addresses of the 2 endpoints of the link"""
        self.q12 = queue.Queue()
        self.q21 = queue.Queue()
        self.l = l * latency
        self.latencyMultiplier = latency
        self.cost = l
        self.e1 = e1
        self.e2 = e2
        self.endtimereached = 0


    def get_e2(self, e1):
        """Returns the other endpoint of the link"""
        if self.e1 == e1:
            return self.e2
        else:
            return self.e1


    def get_cost(self):
        """Returns the cost of the link"""
        return self.cost


    def send_helper(self, packet, src):
        """Runs in a separate thread and sends packet on link from src after waiting for the appropriate latency"""
        if src == self.e1:
            time.sleep(self.l/float(1000))
            if self.endtimereached and packet.content != "1000000":
                pass
            else:
                self.q12.put(packet)
        elif src == self.e2:
            time.sleep(self.l/float(1000))
            if self.endtimereached and packet.content != "1000000":
                pass
            else:
                self.q21.put(packet)


    def send(self, packet, src):
        """Sends 'packet' from 'src' on this link. 
           Checks that packet content is a string and starts a new thread to send it.
           'src' must be equal to self.e1 or self.e2.
        """
        if packet.content:
            assert isinstance((packet.content), str), "Packet content must be a string"
        p = packet.copy()
        _thread.start_new_thread(self.send_helper, (p, src))


    def recv(self, dst, timeout=None):
        """Checks whether a packet is ready to be received by 'dst' on this link.
           'dst' must be equal to self.e1 or self.e2.
           If packet is ready, returns the packet, else returns 'None'.
        """
        if dst == self.e1:
            try:
                packet = self.q21.get_nowait()
                packet.addToRoute(self.e1)
                return packet
            except queue.Empty:
                return None
        elif dst == self.e2:
            try:
                packet = self.q12.get_nowait()
                packet.addToRoute(self.e2)
                return packet
            except queue.Empty:
                return None


    def changeLatency(self, src, c):
        """Update the latency of sending on the link from src"""
        if src == self.e1:
            self.l = c * self.latencyMultiplier
        elif src == self.e2:
            self.l = c * self.latencyMultiplier

