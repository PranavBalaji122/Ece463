#
import time
import sys
import _thread
import queue
import random
from link import Link

class Router():
    """Router class"""

    def __init__(self, addr, lossProb):
        """Initialize Router address and threadsafe queue for link changes"""
        self.addr = addr       # address of router
        self.links = {}        # links indexed by port, i.e., {port:link, ......, port:link}
        self.linkChanges = queue.Queue()
        self.lossProb = lossProb
        self.keepRunning = True
        self.endSimulation = 0
        self.connSetup = 0
        self.connEstablished = 0
        self.connTerminate = 0
        self.f = open("logs/Router-"+self.addr+"-recvd-pkts.dump", "w")
        self.recvdPktCnt = 0
        self.recvdByteCnt = 0


    def changeLink(self, change):
        """Add, remove, or change the cost of a link.
           The 'change' argument is a tuple with first element 'add' or 'remove'.
        """
        self.linkChanges.put(change)


    def addLink(self, port, endpointAddr, link, cost):
        """Add new link to router"""
        self.links = {p:link for p,link in self.links.items() if p != port}
        self.links[port] = link


    def removeLink(self, port):
        """Remove link from router"""
        endpointAddr = None
        for p,link in self.links.items():
            if p == port:
                endpointAddr = link.get_e2(self.addr)
                while not link.q12.empty():
                    link.q12.get_nowait()
                while not link.q21.empty():
                    link.q21.get_nowait()
                break
        self.links = {p:link for p,link in self.links.items() if p != port}


    def runRouter(self):
        """Main loop of router"""
        while self.keepRunning:
            time.sleep(0.1)
            try:
                change = self.linkChanges.get_nowait()
                if change[0] == "add":
                    self.addLink(*change[1:])
                elif change[0] == "remove":
                    self.removeLink(*change[1:])
            except queue.Empty:
                pass
            for port in self.links.keys():
                packet = self.links[port].recv(self.addr)
                if packet:
                    self.handlePacket(port, packet)


    def send(self, port, packet):
        """Send a packet out on given port"""
        try:
            self.links[port].send(packet, self.addr)
        except KeyError:
            pass


    def logRecvdPacket(self, port, outPort, packet, dropped):
        """Log recvd packets"""
        self.recvdPktCnt += 1
        if packet.payload != None:
            self.recvdByteCnt += 10 + len(packet.payload) # 10 bytes for header
        else:
            self.recvdByteCnt += 10 # 10 bytes for header

        if dropped == 0:
            self.f.write("Packet " + str(self.recvdPktCnt) + " - " + "srcAddr: " + packet.srcAddr + " dstAddr: " + packet.dstAddr + " seqNum: " + str(packet.seqNum) + " ackNum: " + str(packet.ackNum) + " SYNFLag: " + str(packet.synFlag) + " ACKFlag: " + str(packet.ackFlag) + " FINFlag: " + str(packet.finFlag) + " Received on port: " + str(port) + " Forwarded on port: " + str(outPort) + " Payload: " + str(packet.payload))
        else:
            self.f.write("Packet " + str(self.recvdPktCnt) + " - " + "srcAddr: " + packet.srcAddr + " dstAddr: " + packet.dstAddr + " seqNum: " + str(packet.seqNum) + " ackNum: " + str(packet.ackNum) + " SYNFLag: " + str(packet.synFlag) + " ACKFlag: " + str(packet.ackFlag) + " FINFlag: " + str(packet.finFlag) + " Received on port: " + str(port) + " Forwarded on port: DROPPED" + " Payload: " + str(packet.payload))
        self.f.write("\n")


    def handlePacket(self, port, packet):
        """Process incoming packet.
           This method is called whenever router receives a packet.
           
           Parameters:
           port : the router port on which the packet was received
           packet : the received packet
        """
        if packet.payload != None: # a data packet
            assert(packet.synFlag == 0 and packet.finFlag == 0)

        if packet.synFlag == 1 or packet.finFlag == 1: # control packet
            assert(packet.payload == None)

        # drop all data packets if connection is not established
        if self.connEstablished == 0 and packet.payload != None:
            self.logRecvdPacket(port, None, packet, 1)
            if port == 1:
                print("[+] ", end='', flush=True)
            elif port == 2:
                print("[@] ", end='', flush=True)
            return

        if packet.synFlag == 1: # connection set up phase
            self.connSetup = 1

        if packet.finFlag == 1: # connection termination phase
            self.connTerminate = 1

        # forwarding and drop logic
        r = random.randint(0, 99)
        if r < self.lossProb and self.connSetup == 0 and self.connTerminate == 0: # drop
            self.logRecvdPacket(port, None, packet, 1)
            if port == 1:
                print("[+] ", end='', flush=True)
            elif port == 2:
                print("[@] ", end='', flush=True)
        else: # forward
            if port == 1:
                self.logRecvdPacket(port, 2, packet, 0)
                self.send(2, packet)
            elif port == 2:
                self.logRecvdPacket(port, 1, packet, 0)
                self.send(1, packet)
            if port == 1:
                print("+ ", end='', flush=True)
            elif port == 2:
                print("@ ", end='', flush=True)

        if self.connSetup == 1: # connection established
            if packet.synFlag == 0 and packet.ackFlag == 1:
                self.connSetup = 0
                self.connEstablished = 1

        if self.connTerminate == 1: # connection terminated
            if packet.finFlag == 0 and packet.ackFlag == 1:
                self.endSimulation = 1

